# OpenTelemetry for Agentic Logging in AWS Bedrock

**Video Tutorial Script**
**Target Duration:** 7-8 minutes
**Audience:** Intermediate developers familiar with AWS and Python, new to OTEL for AI agents

---

## Script Outline

| # | Segment | Duration | Key Points |
|---|---------|----------|------------|
| 1 | Hook & Opening | 0:30 | Pain point of debugging silent agent failures |
| 2 | Why Observability Matters | 1:15 | Debugging, cost tracking, latency monitoring |
| 3 | OTEL: The Industry Standard | 1:30 | Framework-agnostic instrumentation |
| 4 | Container Deployment Requirement | 1:30 | Dockerfile setup with `opentelemetry-instrument` |
| 5 | Viewing Traces in AWS | 1:30 | CLI commands and CloudWatch dashboard |
| 6 | Code Walkthrough | 1:30 | Agent structure and what gets traced |
| 7 | Key Takeaways | 1:00 | 6 best practices |
| 8 | Closing & CTA | 0:15 | Repo link and subscribe |

---

## Segment 1: Hook & Opening (0:30)

### Screen Direction
Split screen - left shows tangled console.log statements, right shows clean trace visualization. Then transition to title card.

### Teleprompter Script

> You built an AI agent. It works on your laptop. You deploy it to production. And then... it just stops responding. No errors. No logs. Just silence.
>
> Debugging AI agents is fundamentally different from debugging traditional applications. Your agent makes decisions. It calls tools. It loops back on itself. And if you can't see inside that black box, you're flying blind.
>
> Today, I'm going to show you how to add full observability to your AI agents using OpenTelemetry — the industry standard that works with whatever framework you're using. CrewAI, AWS ADK, Microsoft Semantic Kernel, LangGraph — it doesn't matter. OpenTelemetry instruments them all.
>
> I'll be using a LangGraph example today, but the concepts apply to any agent framework. And the best part? AWS Bedrock AgentCore handles all the heavy lifting.

---

## Segment 2: Why Observability Matters for AI Agents (1:15)

### Screen Direction
Diagram showing traditional app vs agentic app architecture. Animate a simple request-response flow, then a complex agent flow with branches and loops.

### Teleprompter Script

> First, let's talk about why this matters more for AI agents than traditional applications.
>
> A normal web app? Request comes in, you process it, response goes out. Predictable. Linear. Easy to debug.
>
> An AI agent? The LLM decides what to do next. It might call a tool. It might call five tools. It might loop back and reconsider. The execution path is non-deterministic.
>
> This creates three critical problems:
>
> **One — Debugging.** When your agent gives a wrong answer, where did it go wrong? Was it the LLM? A tool failure? Bad context?
>
> **Two — Cost tracking.** Every LLM call costs money. Every tool invocation adds latency. If your agent is looping unexpectedly, your bill explodes.
>
> **Three — Latency monitoring.** Users expect fast responses. But if your agent is making ten tool calls when it should make two, you need to see that.
>
> So how do we solve this?

---

## Segment 3: OTEL — The Industry Standard (1:30)

### Screen Direction
Show OpenTelemetry logo center stage, then animate logos for CrewAI, AWS ADK, Microsoft Semantic Kernel, and LangGraph appearing around it. Transition to the dependency snippet.

### Framework Support Table
| Framework | OTEL Instrumentation Package |
|-----------|------------------------------|
| LangChain / LangGraph | `opentelemetry-instrumentation-langchain` |
| CrewAI | `opentelemetry-instrumentation-crewai` |
| AWS ADK | Built-in OTEL support |
| Microsoft Semantic Kernel | `opentelemetry-instrumentation-semantic-kernel` |
| Haystack | `opentelemetry-instrumentation-haystack` |

### Teleprompter Script

> Here's the key thing to understand: OpenTelemetry is not tied to any single agent framework. It's the industry standard for observability — backed by the CNCF, supported by every major cloud provider, and used by companies like Google, Microsoft, and Amazon.
>
> What does that mean for you? It means you're not locked in. Whether you're building with CrewAI, AWS's Agent Development Kit, Microsoft Semantic Kernel, Haystack, or LangGraph like I am today — OpenTelemetry has instrumentation libraries for all of them.
>
> The pattern is the same across frameworks:
> - You add an instrumentation package specific to your framework
> - You add the AWS distro to export to X-Ray and CloudWatch
> - Everything else is automatic
>
> For my LangGraph example, that's these two packages. But if you're using CrewAI, you'd swap in `opentelemetry-instrumentation-crewai`. Same concept, different package.

### Code Sample
```python
# pyproject.toml - LangGraph example
dependencies = [
    # Your agent framework (swap this for your framework)
    "langgraph~=1.0.5",
    "langchain-aws~=1.1.0",
    # OpenTelemetry instrumentation (swap for your framework's package)
    "opentelemetry-instrumentation-langchain~=0.45.6",
    # AWS export - same for all frameworks
    "aws-opentelemetry-distro~=0.12.2",
]
```

### Teleprompter Script (continued)

> When you invoke your agent, OpenTelemetry automatically captures:
> - Every LLM invocation with the model, tokens, and latency
> - Every tool call with its inputs and outputs
> - The graph routing decisions — which node ran when and why
> - Even the botocore calls to AWS services like Secrets Manager
>
> Look at this trace output. I can see that my LLM call took 1.2 seconds, but my Tavily search took over 3 seconds. If I want to optimize latency, I know exactly where to look.
>
> But here's the key insight...

### Trace Output Example
```text
Trace: 694561e74067881e... (6 spans, 4293.24ms)
├── chatbot.task [1197.63ms]
│   ├── ChatBedrockConverse.chat [1196.88ms]
│   │   └── chat claude-haiku [1192.09ms]
│   └── tools_condition.task [0.24ms]
└── tools.task [3095.05ms]
    └── tavily_search_results_json.tool [3093.94ms]
```

---

## Segment 4: The Container Deployment Requirement (1:30)

### Screen Direction
Show Dockerfile with CMD line highlighted. Display comparison table of deployment modes.

### Code Sample
```dockerfile
# Install the AWS OpenTelemetry distribution
RUN uv pip install aws-opentelemetry-distro==0.12.2

# The magic happens here
CMD ["opentelemetry-instrument", "python", "-m", "langgraph_agent_web_search"]
```

### Teleprompter Script

> Here's where it gets interesting. You can't just sprinkle OpenTelemetry into your code and call it a day. For auto-instrumentation to work, you need to wrap your Python process.
>
> See that `opentelemetry-instrument` wrapper? That's what makes everything work. It hooks into the Python runtime before your code loads and patches all the instrumented libraries automatically.
>
> This is why container deployment matters. When you deploy to AWS Bedrock AgentCore, you have two options:
>
> Direct code deploy runs your Python file directly — no auto-instrumentation support.
>
> Container deployment builds a Docker image with the wrapper — giving you full instrumentation.
>
> When you run `agentcore configure` and choose container deployment, it generates this Dockerfile for you. The `opentelemetry-instrument` wrapper intercepts LangChain operations, Bedrock runtime calls, HTTP requests from tool calls, and even your logging statements.
>
> And here's the beautiful part — your application code stays clean. No manual trace creation. No context propagation. It just works.
>
> Once deployed, how do you actually view these traces?

### Comparison Table
| Mode | What it does | OTEL Support |
|------|--------------|--------------|
| `direct_code_deploy` | Runs your Python file directly | No auto-instrumentation |
| `container` | Builds a Docker image with wrapper | Full instrumentation |

---

## Segment 5: Viewing Traces in AWS (1:30)

### Screen Direction
Terminal showing agentcore commands. Show example trace list output. Highlight detailed trace breakdown with span timings.

### Code Sample
```bash
# List recent traces
make traces PROFILE=YourProfileName
# or directly:
uv run agentcore obs list

# Get detailed trace breakdown
uv run agentcore obs show --last 1 --verbose
```

### Teleprompter Script

> AWS Bedrock AgentCore integrates with AWS X-Ray and CloudWatch. You can view traces from the command line or the console.
>
> Running `agentcore obs list` gives you a list of recent invocations with their trace IDs and total duration.
>
> For the detailed breakdown, use `agentcore obs show` with the verbose flag.
>
> Let me walk you through what we're seeing here.
>
> - `chatbot.task` — This is the chatbot node in our LangGraph. It invoked the LLM.
> - `ChatBedrockConverse.chat` — The actual Bedrock API call using the Converse API
> - `chat claude-haiku` — The specific model invocation with timing
> - `tools_condition.task` — The routing logic that decided we need to call a tool
> - `tools.task` — The tools node execution
> - `tavily_search_results_json.tool` — The actual Tavily search with its full 3-second latency
>
> You can also view this in the AWS Console. Navigate to CloudWatch, then GenAI Observability, then Agent Core. You'll see dashboards with invocation counts, latency percentiles, token usage over time, and error breakdowns.
>
> Let me show you the actual code that makes this possible...

### Console URL Pattern
```text
https://console.aws.amazon.com/cloudwatch/home?region=<your-region>#gen-ai-observability/agent-core
```

---

## Segment 6: Code Walkthrough (1:30)

### Screen Direction
Show `langgraph_agent_web_search.py` full file. Highlight graph structure, chatbot function, and entrypoint decorator.

### Code Sample — Graph Structure
```python
# Build the graph
# Flow: START -> chatbot -> tools_condition -> tools -> chatbot (loop)
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")
graph = graph_builder.compile()
```

### Code Sample — Chatbot Function
```python
def chatbot(state: State) -> dict[str, list[BaseMessage]]:
    """Chatbot node that invokes the LLM with tools."""
    logger.info("Chatbot node invoked with %d messages", len(state["messages"]))
    response = resilient_llm.invoke(state["messages"])
    logger.info("LLM response received, has tool calls: %s", bool(response.tool_calls))
    return {"messages": [response]}
```

### Code Sample — Entrypoint
```python
@app.entrypoint
def agent_invocation(payload: dict[str, Any], context: Any) -> dict[str, str]:
    """Entry point for Bedrock AgentCore invocations."""
    prompt = payload.get("prompt")
    logger.info("Agent invocation started with prompt length: %d", len(prompt))

    output = graph.invoke(input_state)
    # ...
    return {"result": result}
```

### Teleprompter Script

> Let's look at how this agent is structured and what gets traced.
>
> This is a ReAct-style agent. The chatbot node calls the LLM. If the LLM wants to use a tool, the `tools_condition` routes to the tools node. Then it loops back.
>
> Notice the logger calls in the chatbot function. With OpenTelemetry's logging instrumentation, these get correlated with your traces automatically. When you're debugging, you can see exactly which log message came from which span.
>
> This `@app.entrypoint` decorator is from the Bedrock AgentCore SDK. It creates the root span for your trace. Every operation inside — every LLM call, every tool execution — becomes a child span under this root.
>
> And remember — there are no OpenTelemetry imports in this application code. The instrumentation happens automatically at runtime.
>
> Let me leave you with some practical tips...

---

## Segment 7: Key Takeaways & Best Practices (1:00)

### Screen Direction
Bullet points appearing one by one. End with the two key code snippets.

### Teleprompter Script

> Here are the key things to remember:
>
> **One** — OpenTelemetry is framework-agnostic. I showed LangGraph today, but the same approach works for CrewAI, AWS ADK, Semantic Kernel, and others. Learn OTEL once, use it everywhere.
>
> **Two** — Use container deployment for auto-instrumentation. The `opentelemetry-instrument` wrapper is what makes the magic happen. Direct code deploy doesn't support it.
>
> **Three** — Keep your application code clean. You don't need to import OpenTelemetry or manually create spans. The instrumentation libraries handle it.
>
> **Four** — Use structured logging. Those `logger.info()` calls get correlated with your traces automatically. Future you will thank present you.
>
> **Five** — Monitor your tool latency. In most agents, tool calls — not LLM calls — are the latency bottleneck. The trace visualization makes this obvious.
>
> **Six** — Check the CloudWatch GenAI dashboard. It aggregates across invocations so you can spot patterns — like that 95th percentile latency spike every afternoon.
>
> That's it. Two dependencies. One command wrapper. Full observability — regardless of which agent framework you choose.

### Summary Code Snippets
```python
# pyproject.toml - just these two dependencies
"opentelemetry-instrumentation-langchain~=0.45.6",
"aws-opentelemetry-distro~=0.12.2",
```

```dockerfile
# Dockerfile - the magic line
CMD ["opentelemetry-instrument", "python", "-m", "your_agent"]
```

---

## Segment 8: Closing & CTA (0:15)

### Screen Direction
GitHub repo link overlay + subscribe button animation.

### Teleprompter Script

> The complete code for this sample agent is linked in the description. It includes the CDK infrastructure, the deployment scripts, and everything you need to get started.
>
> If you found this helpful, let me know in the comments what observability challenges you're facing with your AI agents. And I'll see you in the next one.

---

## Production Notes

### B-Roll Suggestions
- Terminal recordings of actual `agentcore obs` commands running
- Screen capture of CloudWatch GenAI Observability dashboard
- Animated diagrams for the trace flow and agent architecture
- Code scrolling through the actual repository files

### Thumbnail Concepts
1. Split image: tangled wires on left, clean organized cables on right, with "AI Agent Debugging" text
2. X-Ray vision glasses looking at a brain (representing seeing inside the agent)
3. Before/after: console.log chaos vs clean trace tree

### Title Options
1. "Stop Flying Blind: OpenTelemetry for AI Agents in AWS Bedrock"
2. "Debug AI Agents Like a Pro with 2 Lines of Code"
3. "The Secret to AI Agent Observability (AWS Bedrock + OpenTelemetry)"

### Repository Link
https://github.com/your-org/langgraph-to-agentcore-sample
