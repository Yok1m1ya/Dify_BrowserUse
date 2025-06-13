"""
import asyncio
import os
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
            # 尝试直接使用asyncio.run()
            result = asyncio.run(self._execute_browser_task(query))
            yield self.create_json_message(result)

        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                # 如果与现有事件循环冲突，回退到手动管理
                print("⚠️ 检测到事件循环冲突，使用手动事件循环管理")
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(self._execute_browser_task(query))
                        yield self.create_json_message(result)
                    finally:
                        loop.close()
                except Exception as fallback_error:
                    yield self.create_json_message({
                        "success": False,
                        "task": query,
                        "result": "",
                        "error": f"回退方案执行失败: {str(fallback_error)}"
                    })
            else:
                # 其他RuntimeError
                yield self.create_json_message({
                    "success": False,
                    "task": query,
                    "result": "",
                    "error": f"Runtime错误: {str(e)}"
                })

        except Exception as e:
            # 其他异常
            yield self.create_json_message({
                "success": False,
                "task": query,
                "result": "",
                "error": f"执行失败: {str(e)}"
            })

    async def _execute_browser_task(self, query: str) -> dict:
        browser_session = None
        agent = None

        try:
            # 初始化LLM - 使用与工作版本相同的配置
            llm = ChatOpenAI(
                model="DeepSeek-R1-32B-FP8",
                openai_api_base="http://10.7.202.237:25010/v1",
                timeout=30,
                max_retries=3,
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
                keep_alive=True,
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
            extend_system_message =
            记住最重要的规则:
            1. 永远不要自动填入任何登录信息，除非用户提供了账户名及密码。
            2. 最后的输出结果,使用中文回答用户。


            extend_planner_system_message =
            以下为补充的重要规则:
            1. 如果遇见"你的连接不是专用连接"、"不安全"、"证书错误"等安全警告页面:
               - 立即寻找"高级"、"Advanced"、"详细信息"等按钮并点击
               - 然后寻找"继续访问"、"继续前往"、"Proceed to"等链接并点击
               - 这些操作是必须的，不要跳过
            2. 如果页面加载失败，请重试一次。
            3. 专注于获取页面的主要内容和信息。


            await browser_session.start()

            # 创建Browser-Use Agent
            agent = Agent(
                task=query,
                llm=llm,
                use_vision=False,
                browser_session=browser_session,
                extend_system_message=extend_system_message,
                extend_planner_system_message=extend_planner_system_message
            )

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
"""

import subprocess
import json
import os
import sys
import tempfile
import time
from collections.abc import Generator
from typing import Any
from pathlib import Path

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

# 禁用遥测
os.environ["ANONYMIZED_TELEMETRY"] = "false"


class DifyBrowseruseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # 获取用户输入的查询指令
        query = tool_parameters.get('query', '').strip()

        if not query:
            yield self.create_json_message({
                "success": False,
                "task": "",
                "result": "",
                "error": "查询指令不能为空"
            })
            return

        # 创建临时文件用于通信
        temp_dir = tempfile.gettempdir()
        task_id = str(int(time.time() * 1000))  # 使用时间戳作为唯一ID
        input_file = Path(temp_dir) / f"browser_task_input_{task_id}.json"
        output_file = Path(temp_dir) / f"browser_task_output_{task_id}.json"

        try:
            # 获取browser_worker.py的路径
            current_dir = Path(__file__).parent
            worker_script = current_dir / "browser_worker_file.py"

            if not worker_script.exists():
                yield self.create_json_message({
                    "success": False,
                    "task": query,
                    "result": "",
                    "error": f"找不到browser_worker_file.py文件，路径: {worker_script}"
                })
                return

            print(f"🚀 开始执行Browser任务: {query}")
            print(f"📂 Worker脚本路径: {worker_script}")
            print(f"📁 临时文件: {input_file}")

            # 写入任务到临时文件
            task_data = {
                "query": query,
                "task_id": task_id
            }

            with open(input_file, 'w', encoding='utf-8') as f:
                json.dump(task_data, f, ensure_ascii=False, indent=2)

            # 准备环境变量
            env = os.environ.copy()
            env["ANONYMIZED_TELEMETRY"] = "false"
            env["OPENAI_API_KEY"] = "fake_key"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            # 启动子进程，传递文件路径
            process = subprocess.Popen([
                sys.executable, str(worker_script), str(input_file), str(output_file)
            ],
                env=env,
                cwd=str(current_dir)
            )

            print("⏳ 等待子进程执行完成...")

            # 等待进程完成或超时
            try:
                return_code = process.wait(timeout=180)  # 3分钟超时

                print(f"🔍 子进程返回码: {return_code}")

                # 读取输出文件
                if output_file.exists():
                    try:
                        with open(output_file, 'r', encoding='utf-8') as f:
                            result = json.load(f)

                        print("✅ 成功读取执行结果")
                        yield self.create_json_message(result)

                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        yield self.create_json_message({
                            "success": False,
                            "task": query,
                            "result": "",
                            "error": f"读取结果文件失败: {str(e)}"
                        })
                else:
                    yield self.create_json_message({
                        "success": False,
                        "task": query,
                        "result": "",
                        "error": f"未找到输出文件，子进程返回码: {return_code}"
                    })

            except subprocess.TimeoutExpired:
                print("⏰ 子进程执行超时，正在终止...")
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()

                yield self.create_json_message({
                    "success": False,
                    "task": query,
                    "result": "",
                    "error": "执行超时（3分钟），子进程已被终止"
                })

        except Exception as e:
            print(f"💥 主进程异常: {str(e)}")
            yield self.create_json_message({
                "success": False,
                "task": query,
                "result": "",
                "error": f"主进程执行失败: {str(e)}"
            })

        finally:
            # 清理临时文件
            try:
                if input_file.exists():
                    input_file.unlink()
                if output_file.exists():
                    output_file.unlink()
                print("🧹 临时文件已清理")
            except Exception as cleanup_error:
                print(f"⚠️ 清理临时文件失败: {cleanup_error}")