import asyncio
import os
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from browser_use import Agent, BrowserSession
from langchain_openai import ChatOpenAI

os.environ["ANONYMIZED_TELEMETRY"] = "false"


class DifyBrowseruseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # 绕过browser-use的OpenAI API key检查
        os.environ["OPENAI_API_KEY"] = "fake_key"

        # 初始化LLM: 使用公司内部的DeepSeek模型
        llm = ChatOpenAI(
            model="DeepSeek-R1-32B-FP8",
            openai_api_base="http://10.7.202.237:25010/v1",
        )

        # 获取用户输入的查询指令
        query = tool_parameters.get('query', '').strip()

        # 执行任务并获取结果
        try:
            print(f"🔄 开始执行任务: {query}")

            # 运行异步任务 - 使用独立的事件循环
            result = asyncio.run(self._execute_agent_task(llm, query))

            # 发送执行结果
            yield self.create_json_message({
                "task": query,
                "result": result,
                "status": "completed"
            })

        except Exception as e:
            # 错误处理
            print(f"❌ 执行失败: {str(e)}")
            yield self.create_json_message({
                "task": query,
                "result": f"执行失败: {str(e)}",
                "status": "error"
            })

    async def _execute_agent_task(self, llm, query: str) -> str:
        browser_session = None
        agent = None

        try:
            print(f"🔄 开始执行任务: {query}")

            # 创建浏览器会话
            browser_session = BrowserSession(
                headless=False,
                viewport={'width': 600, 'height': 400},  # 使用更小的视窗
                context_options={
                    "ignoreHTTPSErrors": True,
                    "acceptDownloads": True,
                    "bypassCSP": True,
                },
                args=[
                    '--ignore-certificate-errors',
                    '--ignore-ssl-errors',
                    '--disable-web-security',
                    '--allow-running-insecure-content',
                ]
            )

            extend_system_message = """
            记住最重要的几条规则:
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
                extend_planner_system_message=extend_planner_system_message,
            )

            print("✅ 浏览器会话和Agent创建完成")

            # 执行任务
            history = await agent.run()

            print("✅ 任务执行完成")
            print(f"🔍 结果类型: {type(history)}")

            # 获取最终结果
            final_result = history.final_result()
            print(f"🔍 final_result: {final_result}")

            if final_result:
                print("📄 获取到最终结果")
                return str(final_result)

            # 备用方案1：从extracted_content获取
            extracted_content = history.extracted_content()
            if extracted_content:
                print(f"🔍 使用extracted_content，共{len(extracted_content)}项")
                last_content = extracted_content[-1] if extracted_content else "未找到提取的内容"
                print(f"📄 最后提取的内容: {last_content}")
                return str(last_content)

            # 备用方案2：检查完成状态
            is_done = history.is_done()
            print(f"🔍 任务完成状态: {is_done}")

            if is_done:
                return "任务已完成，但未获取到具体结果内容"
            else:
                return "任务未完成"

        except Exception as e:
            print(f"❌ Agent执行错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Agent执行错误: {str(e)}"

        finally:
            # 确保浏览器会话被正确关闭 - 关键修复点
            print("🔄 开始清理资源...")
            try:
                if agent and hasattr(agent, 'browser_session') and agent.browser_session:
                    await agent.browser_session.close()
                    print("🧹 通过Agent清理浏览器会话成功")
                elif browser_session:
                    await browser_session.close()
                    print("🧹 直接清理浏览器会话成功")
            except Exception as cleanup_error:
                print(f"⚠️ 清理浏览器会话时出错: {cleanup_error}")

            print("🔄 资源清理流程完成")