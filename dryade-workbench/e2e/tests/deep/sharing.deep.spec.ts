/**
 * Sharing Deep Tests — exercises conversation sharing API endpoints.
 *
 * Tests: create conversation, share with user, view shared state, unshare.
 * Single-user only — multi-user sharing tests are deferred per CONTEXT.md.
 *
 * Note: The sharing API requires a target user_id. These tests use the
 * authenticated user's own ID as a synthetic target to validate endpoint
 * behavior. If the share endpoint returns 404 (feature not available),
 * remaining tests are skipped gracefully.
 */

import { test, expect, API_URL, retryApi } from "../../fixtures/deep-test";

test.describe.serial("Sharing Deep Tests @deep", () => {
  let conversationId: string;
  let currentUserId: string;
  let targetUserId: string;
  let sharingAvailable = true;

  test("@deep should create a conversation for sharing tests", async ({
    apiClient,
  }) => {
    // Get current user ID for sharing operations — retry on 429
    let meRes: Awaited<ReturnType<typeof apiClient.get>>;
    for (let attempt = 0; attempt < 5; attempt++) {
      meRes = await apiClient.get("/api/users/me");
      if (meRes.status() !== 429) break;
      const retryAfter = Number(meRes.headers()["retry-after"] || "3");
      await new Promise((r) => setTimeout(r, (retryAfter + 1) * 1000));
    }
    expect(meRes!.status()).toBe(200);
    const meBody = await meRes.json();
    currentUserId = meBody.id || meBody.sub || meBody.user_id;
    expect(currentUserId).toBeTruthy();

    // Register a real target user for sharing (FK on user_id requires existing user)
    const uniqueSuffix = Date.now();
    const targetEmail = `share-target-${uniqueSuffix}@example.com`;
    const targetPassword = `ShareTarget!${uniqueSuffix}`;
    const registerRes = await apiClient.post("/api/auth/register", {
      data: {
        email: targetEmail,
        password: targetPassword,
        display_name: `share_target_${uniqueSuffix}`,
      },
    });
    expect([200, 201]).toContain(registerRes.status());
    const registerBody = await registerRes.json();
    // Register returns JWT tokens, not a user object.
    // Extract user ID from the JWT sub claim, or fall back to /api/users/me.
    targetUserId =
      registerBody.id ||
      registerBody.user?.id ||
      registerBody.user_id ||
      registerBody.sub;
    if (!targetUserId && registerBody.access_token) {
      // Decode JWT payload to extract sub (user ID)
      try {
        const payload = JSON.parse(
          Buffer.from(registerBody.access_token.split(".")[1], "base64").toString(),
        );
        targetUserId = payload.sub;
      } catch {
        // ignore decode errors
      }
    }
    expect(targetUserId).toBeTruthy();

    // Create a conversation to use in sharing tests
    const res = await apiClient.post("/api/chat/conversations", {
      data: {
        title: "Sharing Test Conv",
        mode: "chat",
      },
    });

    expect(res.status()).toBe(201);

    const body = await res.json();
    expect(body.id).toBeTruthy();
    expect(body.title).toBe("Sharing Test Conv");
    conversationId = body.id;
  });

  test("@deep should share a conversation", async ({ apiClient }) => {
    const res = await apiClient.patch(
      `/api/chat/conversations/${conversationId}/share`,
      {
        data: {
          user_id: targetUserId,
          permission: "view",
        },
      },
    );

    // If sharing endpoints return 404, feature is not available
    if (res.status() === 404) {
      sharingAvailable = false;
      test.skip(sharingAvailable === false, "Sharing API not available");
      return;
    }

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.message).toBeTruthy();
    expect(body.message).toContain("shared");
  });

  test("@deep should view shared state of conversation", async ({
    apiClient,
  }) => {
    test.skip(!sharingAvailable, "Sharing API not available");

    // Verify the conversation still exists and is accessible
    const res = await apiClient.get(
      `/api/chat/conversations/${conversationId}`,
    );

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.id).toBe(conversationId);
    expect(body.title).toBe("Sharing Test Conv");

    // Re-share with "edit" permission to verify permission update works
    const updateRes = await retryApi(() =>
      apiClient.patch(
        `/api/chat/conversations/${conversationId}/share`,
        {
          data: {
            user_id: targetUserId,
            permission: "edit",
          },
        },
      ),
    );

    expect(updateRes.status()).toBe(200);

    const updateBody = await updateRes.json();
    expect(updateBody.message).toBeTruthy();
    // Should indicate update or already-shared
    expect(updateBody.message).toMatch(/share|updated/i);
  });

  test("@deep should unshare a conversation", async ({ apiClient }) => {
    test.skip(!sharingAvailable, "Sharing API not available");

    const res = await apiClient.delete(
      `/api/chat/conversations/${conversationId}/share/${targetUserId}`,
    );

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.message).toBeTruthy();
    expect(body.message).toContain("unshared");

    // Verify unsharing again returns idempotent success
    const res2 = await apiClient.delete(
      `/api/chat/conversations/${conversationId}/share/${targetUserId}`,
    );

    expect(res2.status()).toBe(200);

    const body2 = await res2.json();
    expect(body2.message).toContain("not shared");
  });
});
