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

        # 初始化Browser
        browser_session = BrowserSession(
            headless=True,
            viewport={'width': 964, 'height': 647},
            context_options={
                "ignoreHTTPSErrors": True,
                "acceptDownloads": True,
                "bypassCSP": True,
            },
            args=[
                '--ignore-certificate-errors',  # 忽略证书错误
                '--ignore-ssl-errors',  # 忽略SSL错误
                '--disable-web-security',  # 禁用网络安全检查
                '--allow-running-insecure-content',  # 允许不安全内容
            ]
        )

        # 设置扩展系统提示
        extend_planner_system_message = """
            以下为重要的规则:
            1. 最后的输出结果,使用中文回答用户。
            2. 如果遇见"你的连接不是专用连接"、"不安全"、"证书错误"等安全警告页面:
               - 立即寻找"高级"、"Advanced"、"详细信息"等按钮并点击
               - 然后寻找"继续访问"、"继续前往"、"Proceed to"等链接并点击
               - 这些操作是必须的，不要跳过
            3. 如果遇见付费墙、验证码验证或登录需求时直接跳过并说明情况。
            4. 如果页面加载失败，请重试一次。
            5. 专注于获取页面的主要内容和信息。
            6. 优先提取页面文本内容，忽略复杂的交互元素。
        """

        # 获取用户输入的查询指令
        query = tool_parameters.get('query', '').strip()

        # 创建Browser-Use Agent
        agent = Agent(
            task=query,
            llm=llm,
            use_vision=False,
            browser_session=browser_session,
            extend_planner_system_message=extend_planner_system_message,
        )

        # 执行任务并获取结果
        try:
            # 运行异步任务
            result = asyncio.run(self._execute_agent(agent, query))

            # 发送执行结果
            yield self.create_json_message({
                "task": query,
                "result": result,
                "status": "completed"
            })

        except Exception as e:
            # 错误处理
            yield self.create_json_message({
                "task": query,
                "result": f"执行失败: {str(e)}",
                "status": "error"
            })


    async def _execute_agent(self, agent: Agent, query: str) -> str:
        """执行Browser-Use Agent的异步方法"""
        try:
            # 执行任务
            history = await agent.run()

            # 获取最终结果
            final_result = history.final_result()

            if final_result:
                return str(final_result)

        except Exception as e:
            return f"Agent执行错误: {str(e)}"
        finally:
            # 确保浏览器会话被正确关闭
            try:
                if hasattr(agent, 'browser_session') and agent.browser_session:
                    await agent.browser_session.close()
            except Exception as cleanup_error:
                print(f"清理浏览器会话时出错: {cleanup_error}")