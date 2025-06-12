from langchain_openai import ChatOpenAI
from browser_use import Agent, BrowserSession
import asyncio
import os
from dotenv import load_dotenv
import logging

os.environ["ANONYMIZED_TELEMETRY"] = "false"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

# 初始化Browser
browser_session = BrowserSession(
    headless=False,
    viewport={'width': 600, 'height': 400},
    context_options={
        "ignoreHTTPSErrors": True,
        "acceptDownloads": True,
        "bypassCSP": True,
    },
    args=[
        '--ignore-certificate-errors',      # 忽略证书错误
        '--ignore-ssl-errors',              # 忽略SSL错误
        '--disable-web-security',           # 禁用网络安全检查
        '--allow-running-insecure-content', # 允许不安全内容
    ]
)

# 绕过browser-use的OpenAI API key检查
os.environ["OPENAI_API_KEY"] = "fake_key"

# 初始化LLM: 使用公司内部的DeepSeek模型
llm = ChatOpenAI(
    model="DeepSeek-R1-32B-FP8",
    openai_api_base="http://10.7.202.237:25010/v1",
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

task = "在url栏输入：https://10.2.158.10/coremail/index.jsp?cus=1， 总结页面信息"

# 创建Browser-Use Agent
agent = Agent(
    task=task,
    llm=llm,
    use_vision=False,
    browser_session=browser_session,
    extend_system_message=extend_system_message,
    extend_planner_system_message=extend_planner_system_message
)


async def execute_agent(agent: Agent, query: str) -> str:
    """执行Browser-Use Agent的异步方法"""
    try:
        print(f"🔄 开始执行任务: {query}")

        # 执行任务
        history = await agent.run()

        print("✅ 任务执行完成")
        print(f"🔍 结果类型: {type(history)}")

        # 获取最终结果
        final_result = history.final_result()
        print(f"🔍 final_result: {final_result}")

        if final_result:
            print("📄 获取到最终结果:")
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
        # 确保浏览器会话被正确关闭
        try:
            if hasattr(agent, 'browser_session') and agent.browser_session:
                await agent.browser_session.close()
                print("🧹 浏览器会话已关闭")
        except Exception as cleanup_error:
            print(f"⚠️ 清理浏览器会话时出错: {cleanup_error}")


async def main():
    """主函数"""
    print("=" * 60)
    print("🌐 Browser-Use 独立测试")
    print("=" * 60)
    print(f"📝 任务: {task}")
    print("=" * 60)

    try:
        # 执行Agent
        result = await execute_agent(agent, task)

        print("\n" + "=" * 60)
        print("📊 执行结果:")
        print("=" * 60)
        print(result)
        print("=" * 60)

        return result

    except Exception as e:
        print(f"❌ 主程序执行错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"主程序执行错误: {str(e)}"


if __name__ == "__main__":
    # 运行异步主函数
    result = asyncio.run(main())
    print(f"\n🎯 最终返回结果: {result}")