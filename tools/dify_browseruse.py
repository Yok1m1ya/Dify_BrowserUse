import asyncio
import os
import time
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

        try:
            # 直接在当前线程中运行异步任务（保持工作版本的执行模式）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                result = loop.run_until_complete(self._execute_browser_task(query))

                # 返回最终结果
                yield self.create_json_message(result)

            finally:
                loop.close()

        except Exception as e:
            # 返回错误结果
            yield self.create_json_message({
                "success": False,
                "task": query,
                "result": "",
                "error": f"执行失败: {str(e)}"
            })

    async def _execute_browser_task(self, query: str) -> dict:
        """执行Browser-Use任务的异步方法 - 完全复制工作版本的逻辑"""
        browser_session = None
        agent = None

        try:
            # 初始化LLM - 使用与工作版本相同的配置
            llm = ChatOpenAI(
                model="DeepSeek-R1-32B-FP8",
                openai_api_base="http://10.7.202.237:25010/v1",
            )

            # 初始化浏览器会话 - 完全复制工作版本的配置
            browser_session = BrowserSession(
                headless=False,  # Dify环境中必须使用无头模式
                viewport={'width': 600, 'height': 400},
                context_options={
                    "ignoreHTTPSErrors": True,
                    "acceptDownloads": True,
                    "bypassCSP": True,
                },
                args=[
                    '--no-sandbox',  # Dify容器环境必需
                    '--disable-dev-shm-usage',  # 避免共享内存问题
                    '--disable-gpu',  # 禁用GPU
                    '--ignore-certificate-errors',  # 复制工作版本的SSL设置
                    '--ignore-ssl-errors',
                    '--disable-web-security',
                    '--allow-running-insecure-content',
                ]
            )

            # 系统消息配置 - 完全复制工作版本
            extend_system_message = """
            记住最重要的规则:
            1. 永远不要自动填入任何登录信息，除非用户提供了账户名及密码。
            2. 最后的输出结果,使用中文回答用户。
            """

            extend_planner_system_message = """
            以下为补充的重要规则:
            1. 如果遇见"你的连接不是专用连接"、"不安全"、"证书错误"等安全警告页面:
               - 立即寻找"高级"、"Advanced"、"详细信息"等按钮并点击
               - 然后寻找"继续访问"、"继续前往"、"Proceed to"等链接并点击
               - 这些操作是必须的，不要跳过
            2. 如果页面加载失败，请重试一次。
            3. 专注于获取页面的主要内容和信息。
            4. 优先提取页面文本内容，忽略复杂的交互元素。
            """

            # 创建Browser-Use Agent
            agent = Agent(
                task=query,
                llm=llm,
                use_vision=False,
                browser_session=browser_session,
                extend_system_message=extend_system_message,
                extend_planner_system_message=extend_planner_system_message
            )

            # 执行任务
            history = await agent.run()

            # 获取最终结果 - 完全复制工作版本的多层级获取策略
            final_result = history.final_result()

            if final_result:
                return {
                    "success": True,
                    "task": query,
                    "result": str(final_result),
                    "error": ""
                }

            # 备用方案1：从extracted_content获取
            extracted_content = history.extracted_content()
            if extracted_content:
                last_content = extracted_content[-1] if extracted_content else "未找到提取的内容"
                return {
                    "success": True,
                    "task": query,
                    "result": str(last_content),
                    "error": ""
                }

            # 备用方案2：检查完成状态
            is_done = history.is_done()

            if is_done:
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
            # 确保浏览器会话被正确关闭 - 完全复制工作版本的清理逻辑
            try:
                if agent and hasattr(agent, 'browser_session') and agent.browser_session:
                    await agent.browser_session.close()
                elif browser_session:
                    await browser_session.close()
            except Exception as cleanup_error:
                # 在Dify环境中，清理错误不应该影响最终结果
                pass