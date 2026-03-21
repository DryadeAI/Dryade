---
title: "Visual Workflow Builder"
sidebar_position: 3
---

# Visual Workflow Builder

The Workflow Builder lets you create automated processes using a visual drag-and-drop canvas. Chain together AI steps, human approvals, conditions, and integrations to build repeatable workflows.

![Workflow builder canvas with connected nodes — trigger, AI action, condition, approval, and output](/img/screenshots/workflow-builder.png)

## What Workflows Are

Workflows are visual automation sequences that run a series of steps in order. Each step is represented as a **node** on a canvas, and connections between nodes define the execution flow.

Use workflows when you want to:

- **Automate repetitive tasks** -- Turn a multi-step process into a one-click execution
- **Add human checkpoints** -- Require approval before critical steps proceed
- **Chain AI operations** -- Pass output from one AI step as input to the next
- **Schedule recurring work** -- Run workflows on a schedule without manual intervention

## Creating a Workflow

1. Go to **Workflows** in the sidebar
2. Click **Create Workflow**
3. Give your workflow a name and description
4. The visual canvas opens, ready for you to add nodes

### Adding Nodes

Drag nodes from the node palette onto the canvas. Each node represents one step in your workflow:

| Node Type | Purpose | Example |
|-----------|---------|---------|
| **Trigger** | Starts the workflow | Manual trigger, scheduled trigger, webhook |
| **AI Action** | Runs an AI operation | Generate text, analyze data, classify input |
| **Tool Action** | Calls an external tool | Send email, create issue, update database |
| **Condition** | Branches based on logic | If score > 80, if status == "approved" |
| **Approval** | Pauses for human review | Manager approval before deployment |
| **Transform** | Modifies data between steps | Format output, merge results, filter items |

### Connecting Nodes

Connect nodes by dragging from one node's output port to another node's input port. The connection defines the order of execution and how data flows between steps.

- **Sequential flow** -- Connect nodes in a chain for step-by-step execution
- **Branching** -- Use condition nodes to split the flow based on results
- **Merging** -- Multiple branches can converge back to a single node

### Configuring Nodes

Click on any node to open its configuration panel:

- **AI Action nodes** -- Set the prompt template, model, and output format
- **Condition nodes** -- Define the condition expression and branch labels
- **Approval nodes** -- Specify who needs to approve and the timeout
- **Tool nodes** -- Configure the tool parameters and connection details

## Running Workflows

### Manual Execution

1. Open the workflow you want to run
2. Click **Run** in the toolbar
3. If the workflow has input parameters, fill them in
4. Watch the execution progress on the canvas

Each node highlights as it executes, and you can see the output of each step in real time.

### Scheduled Execution

Set up workflows to run automatically:

1. Open the workflow settings
2. Configure the schedule (hourly, daily, weekly, or cron expression)
3. Save -- the workflow will run at the specified times

### Webhook Triggers

Trigger workflows from external events:

1. Add a webhook trigger node to your workflow
2. Copy the generated webhook URL
3. Send a POST request to that URL to start the workflow

## Monitoring Execution

While a workflow runs, the canvas provides real-time feedback:

- **Active node** -- The currently executing node is highlighted
- **Completed nodes** -- Successfully finished nodes show a green indicator
- **Failed nodes** -- Nodes that encountered an error show a red indicator
- **Pending approval** -- Approval nodes waiting for human review show an amber indicator

### Execution History

View past runs from the workflow detail page:

- **Run list** -- See all previous executions with status and duration
- **Step details** -- Click into a run to see input/output for each node
- **Error details** -- Failed runs show the error message and which node failed

## Approval Workflows

Approval nodes pause execution until a human reviews and approves:

1. The workflow reaches the approval node and pauses
2. The designated approver receives a notification
3. The approver reviews the data and either approves or rejects
4. On approval, the workflow continues; on rejection, it stops or takes an alternative path

This is essential for workflows that involve:

- Deploying to production
- Sending communications to customers
- Making financial transactions
- Any step where human judgment is required

## Templates

Dryade includes predefined workflow templates to help you get started:

- **Content review** -- Generate content with AI, review with a human, then publish
- **Data processing** -- Import data, transform it, validate results
- **Incident response** -- Detect an issue, gather context, notify the team, track resolution

To use a template:

1. Click **Create Workflow**
2. Select **From Template**
3. Choose a template and customize it for your needs

## Tips

- **Start simple.** Build a basic workflow first, verify it works, then add complexity. It is easier to debug a workflow with 3 nodes than one with 30.
- **Use approval nodes for critical steps.** Even if you trust the AI, adding a human checkpoint before irreversible actions prevents mistakes.
- **Name your nodes clearly.** Descriptive node names make workflows easier to understand and debug. "Generate quarterly report" is better than "AI Step 1."
- **Test with small inputs.** Before running a workflow on production data, test it with a small sample to verify the output.
- **Check execution history.** When a workflow does not produce the expected results, review the step-by-step execution to identify where things went wrong.
