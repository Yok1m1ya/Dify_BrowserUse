import asyncio
import os
import concurrent.futures
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from browser_use import Agent, BrowserSession
from langchain_openai import ChatOpenAI

# 禁用遥测
os.environ["ANONYMIZED_TELEMETRY"] = "false"


class DifyBrowseruseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # 绕过browser-use的OpenAI API key检查
        os.environ["OPENAI_API_KEY"] = "fake_key"

        # 获取用户输入的查询指令
        query = tool_parameters.get('query', '').strip()

        if not query:
            yield self.create_json_message({
                "success": False,
                "error": "查询参数不能为空",
                "task": "",
                "result": ""
            })
            return

        try:
            # 使用线程池执行异步任务，避免事件循环冲突
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(self._run_browser_task, query)
                # 设置超时时间为5分钟
                result = future.result(timeout=300)

            # 返回结果
            yield self.create_json_message(result)

        except concurrent.futures.TimeoutError:
            # 超时处理
            yield self.create_json_message({
                "success": False,
                "task": query,
                "result": "",
                "error": "任务执行超时（5分钟）"
            })
        except Exception as e:
            # 返回错误结果
            yield self.create_json_message({
                "success": False,
                "task": query,
                "result": "",
                "error": f"执行失败: {str(e)}"
            })

    def _run_browser_task(self, query: str) -> dict:
        """在新线程中运行异步任务"""
        try:
            # 在新线程中创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                return loop.run_until_complete(self._execute_browser_task(query))
            finally:
                loop.close()

        except Exception as e:
            return {
                "success": False,
                "task": query,
                "result": "",
                "error": f"线程执行错误: {str(e)}"
            }

    async def _execute_browser_task(self, query: str) -> dict:
        """执行Browser-Use任务的异步方法"""
        browser_session = None
        agent = None

        try:
            # 初始化LLM - 增加超时设置
            llm = ChatOpenAI(
                model="DeepSeek-R1-32B-FP8",
                openai_api_base="http://10.7.202.237:25010/v1",
                timeout=120,  # 2分钟超时
                request_timeout=120,
                max_retries=2
            )

            # 初始化浏览器会话 - 简化配置
            browser_session = BrowserSession(
                headless=False,  # 在Dify环境中使用无头模式
                viewport={'width': 600, 'height': 400},
                context_options={
                    "ignoreHTTPSErrors": True,
                    "acceptDownloads": False,  # 禁用下载避免权限问题
                    "bypassCSP": True,
                },
                args=[
                    '--no-sandbox',  # 在容器环境中必需
                    '--disable-dev-shm-usage',  # 避免共享内存问题
                    '--disable-gpu',  # 禁用GPU
                    '--ignore-certificate-errors',
                    '--ignore-ssl-errors',
                    '--disable-web-security',
                    '--allow-running-insecure-content',
                ]
            )

            # 系统消息配置 - 简化
            extend_system_message = """
            重要规则:
            1. 永远不要自动填入登录信息，除非用户明确提供。
            2. 使用中文回答用户。
            3. 快速完成任务，避免不必要的操作。
            """

            extend_planner_system_message = """
            执行规则:
            1. 遇到安全警告页面时，寻找"高级"或"继续访问"按钮并点击。
            2. 如果页面加载失败，重试一次。
            3. 专注于获取主要内容，忽略复杂交互。
            4. 尽快完成任务。
            """

            # 创建Browser-Use Agent - 添加限制
            agent = Agent(
                task=query,
                llm=llm,
                use_vision=False,
                browser_session=browser_session,
                extend_system_message=extend_system_message,
                extend_planner_system_message=extend_planner_system_message,
            )

            # 执行任务 - 添加超时保护
            try:
                history = await asyncio.wait_for(agent.run(), timeout=240)  # 4分钟超时
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "task": query,
                    "result": "",
                    "error": "Browser-Use任务执行超时"
                }

            # 获取最终结果
            final_result = history.final_result()
            if final_result:
                return {
                    "success": True,
                    "task": query,
                    "result": str(final_result),
                    "error": ""
                }

            # 备用方案：从extracted_content获取
            extracted_content = history.extracted_content()
            if extracted_content:
                last_content = extracted_content[-1] if extracted_content else "未找到提取的内容"
                return {
                    "success": True,
                    "task": query,
                    "result": str(last_content),
                    "error": ""
                }

            # 检查完成状态
            if history.is_done():
                return {
                    "success": True,
                    "task": query,
                    "result": "任务已完成，但未获取到具体结果内容",
                    "error": ""
                }
            else:
                return {
                    "success": False,
                    "task": query,
                    "result": "",
                    "error": "任务未完成"
                }

        except Exception as e:
            return {
                "success": False,
                "task": query,
                "result": "",
                "error": f"Agent执行错误: {str(e)}"
            }

        finally:
            # 强制清理资源
            try:
                if agent and hasattr(agent, 'browser_session') and agent.browser_session:
                    await agent.browser_session.close()
                elif browser_session:
                    await browser_session.close()
            except Exception:
                pass

            # 额外清理：强制关闭可能残留的浏览器进程
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name']):
                    if 'chrome' in proc.info['name'].lower() or 'chromium' in proc.info['name'].lower():
                        try:
                            proc.terminate()
                        except:
                            pass
            except ImportError:
                pass  # psutil未安装时忽略