/**
 * Per-scenario expected topology and node count map.
 *
 * Used by execution tests to assert that a given scenario produces
 * the expected number of node events, router activations, and graph shape.
 */

export interface ScenarioExpectations {
  minNodes: number;
  hasRouter: boolean;
  topology: "linear" | "router" | "parallel" | "dag";
  requiredNodeIds?: string[]; // key node IDs that must appear in events
  routerShouldActivate?: string; // one of the router branch labels
}

/**
 * Expected characteristics for all 10 distinct workflow scenarios.
 *
 * minNodes: minimum number of node_complete events expected
 * hasRouter: whether the workflow has at least one router node
 * topology: graph shape (linear=no branches, router=conditional, parallel=fan-out, dag=mixed)
 */
export const SCENARIO_EXPECTATIONS: Record<string, ScenarioExpectations> = {
  sprint_planning: {
    minNodes: 13,
    hasRouter: true,
    topology: "dag",
  },
  invoice_processing: {
    minNodes: 9,
    hasRouter: true,
    topology: "router",
  },
  devops_deployment: {
    minNodes: 9,
    hasRouter: true,
    topology: "router",
  },
  customer_onboarding: {
    minNodes: 10,
    hasRouter: true,
    topology: "router",
  },
  prospect_research: {
    minNodes: 8,
    hasRouter: false,
    topology: "parallel",
  },
  multi_framework_demo: {
    minNodes: 8,
    hasRouter: true,
    topology: "router",
  },
  code_review_pipeline: {
    minNodes: 9,
    hasRouter: true,
    topology: "router",
  },
  compliance_audit: {
    minNodes: 9,
    hasRouter: true,
    topology: "router",
  },
  financial_reporting: {
    minNodes: 6,
    hasRouter: false,
    topology: "linear",
  },
  data_pipeline: {
    minNodes: 5,
    hasRouter: false,
    topology: "linear",
  },
};
