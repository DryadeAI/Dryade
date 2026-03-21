/**
 * Projects Deep Tests — exercises the full project lifecycle via API.
 *
 * Tests: create with name/color, rename, move conversation into project,
 * view project with conversation count, archive, delete.
 */

import { test, expect, retryApi } from "../../fixtures/deep-test";

test.describe.serial("Projects Deep Tests @deep", () => {
  let projectId: string;
  let conversationId: string;

  test("@deep should create a project with name and color", async ({
    apiClient,
  }) => {
    let res: Awaited<ReturnType<typeof apiClient.post>>;
    for (let attempt = 0; attempt < 5; attempt++) {
      res = await apiClient.post("/api/projects", {
        data: {
          name: "Deep Test Project",
          color: "#3B82F6",
        },
      });
      if (res.status() !== 429) break;
      const retryAfter = Number(res.headers()["retry-after"] || "3");
      await new Promise((r) => setTimeout(r, (retryAfter + 1) * 1000));
    }
    expect(res!.status()).toBe(201);

    const body = await res.json();
    expect(body.id).toBeTruthy();
    expect(body.name).toBe("Deep Test Project");
    expect(body.color).toBe("#3B82F6");
    expect(body.is_archived).toBe(false);
    expect(body.conversation_count).toBe(0);

    projectId = body.id;
  });

  test("@deep should rename a project", async ({ apiClient }) => {
    const res = await retryApi(() =>
      apiClient.patch(`/api/projects/${projectId}`, {
        data: {
          name: "Renamed Deep Project",
        },
      }),
    );

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.name).toBe("Renamed Deep Project");

    // Verify via direct GET
    const getRes = await apiClient.get(`/api/projects/${projectId}`);
    expect(getRes.status()).toBe(200);

    const getBody = await getRes.json();
    expect(getBody.name).toBe("Renamed Deep Project");
  });

  test("@deep should move a conversation into project", async ({
    apiClient,
  }) => {
    // First, create a conversation to move — retry on 429
    let createRes: Awaited<ReturnType<typeof apiClient.post>>;
    for (let attempt = 0; attempt < 5; attempt++) {
      createRes = await apiClient.post("/api/chat/conversations", {
        data: {
          title: "Project Test Conv",
          mode: "chat",
        },
      });
      if (createRes.status() !== 429) break;
      const retryAfter = Number(createRes.headers()["retry-after"] || "3");
      await new Promise((r) => setTimeout(r, (retryAfter + 1) * 1000));
    }
    expect(createRes!.status()).toBe(201);
    const convBody = await createRes.json();
    expect(convBody.id).toBeTruthy();
    conversationId = convBody.id;

    // Move conversation into the project
    const moveRes = await retryApi(() =>
      apiClient.patch(
        `/api/chat/conversations/${conversationId}/project`,
        {
          data: {
            project_id: projectId,
          },
        },
      ),
    );

    expect(moveRes.status()).toBe(200);

    const moveBody = await moveRes.json();
    expect(moveBody.project_id).toBe(projectId);
  });

  test("@deep should view project with conversation count", async ({
    apiClient,
  }) => {
    // Verify conversation count via API
    const res = await apiClient.get("/api/projects");
    expect(res.status()).toBe(200);

    const body = await res.json();
    const projects = body.projects ?? (Array.isArray(body) ? body : []);
    const project = projects.find(
      (p: { id: string }) => p.id === projectId,
    );
    expect(project).toBeTruthy();
    expect(project.conversation_count).toBeGreaterThanOrEqual(1);
  });

  test("@deep should archive a project", async ({ apiClient }) => {
    const res = await apiClient.patch(`/api/projects/${projectId}`, {
      data: {
        is_archived: true,
      },
    });

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.is_archived).toBe(true);

    // Verify archived project is excluded from default list
    const listRes = await apiClient.get("/api/projects");
    expect(listRes.status()).toBe(200);

    const listBody = await listRes.json();
    const found = listBody.projects.find(
      (p: { id: string }) => p.id === projectId,
    );
    expect(found).toBeFalsy();

    // Verify it appears when include_archived=true
    const archivedRes = await apiClient.get(
      "/api/projects?include_archived=true",
    );
    expect(archivedRes.status()).toBe(200);

    const archivedBody = await archivedRes.json();
    const archivedProject = archivedBody.projects.find(
      (p: { id: string }) => p.id === projectId,
    );
    expect(archivedProject).toBeTruthy();
    expect(archivedProject.is_archived).toBe(true);
  });

  test("@deep should delete a project", async ({ apiClient }) => {
    const res = await apiClient.delete(`/api/projects/${projectId}`);

    expect([200, 204]).toContain(res.status());

    // Verify project is gone from list
    const listRes = await apiClient.get(
      "/api/projects?include_archived=true",
    );
    expect(listRes.status()).toBe(200);

    const listBody = await listRes.json();
    const found = listBody.projects.find(
      (p: { id: string }) => p.id === projectId,
    );
    expect(found).toBeFalsy();
  });
});
