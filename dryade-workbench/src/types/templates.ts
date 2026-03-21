// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Template types for the Templates plugin.
 *
 * Matches the backend Pydantic schemas from plugins/templates/schemas.py
 */

/** Predefined template categories (matches backend CATEGORIES) */
export const TEMPLATE_CATEGORIES = [
  "Data Analysis",
  "Sales",
  "DevOps",
  "Research",
  "Customer Support",
  "HR",
] as const;

export type TemplateCategory = typeof TEMPLATE_CATEGORIES[number];

/** Workflow node stored in template */
export interface TemplateNode {
  id: string;
  type: string;
  label: string;
  description?: string;
  agent?: string;
  task?: string;
  position: { x: number; y: number };
}

/** Workflow edge stored in template */
export interface TemplateEdge {
  id: string;
  from: string;
  to: string;
}

/** Workflow JSON structure stored in template */
export interface TemplateWorkflowJson {
  nodes: TemplateNode[];
  edges: TemplateEdge[];
}

/** Full template object from API */
export interface Template {
  id: number;
  user_id: string;
  name: string;
  description: string | null;
  category: TemplateCategory;
  tags: string[];
  workflow_json: TemplateWorkflowJson;
  created_at: string;
  updated_at: string;
}

/** Request to create a new template */
export interface CreateTemplateRequest {
  name: string;
  description?: string;
  category: TemplateCategory;
  tags?: string[];
  workflow_json: TemplateWorkflowJson;
}

/** Request to update a template */
export interface UpdateTemplateRequest {
  name?: string;
  description?: string;
  category?: TemplateCategory;
  tags?: string[];
}

/** Response from list templates endpoint */
export interface TemplatesListResponse {
  templates: Template[];
}

/** Response from categories endpoint */
export interface CategoriesResponse {
  categories: TemplateCategory[];
}
