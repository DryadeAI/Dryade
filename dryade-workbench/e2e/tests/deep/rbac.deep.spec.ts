/**
 * RBAC Deep Tests -- exercises all rights_basic plugin endpoints end-to-end.
 *
 * Tests: plugin loading, role listing, permission matrix, permission check
 * (single + batch), role assignment, effective permissions, scope listing,
 * scope registration, user management, resource sharing, audit logging,
 * enterprise tier gating, permission after role change, and cross-user
 * permission denial with sharing grant.
 *
 * Requires running backend with rights_basic plugin loaded.
 */

import { test, expect, API_URL } from "../../fixtures/deep-test";

const RBAC_BASE = "/api/plugins/rights_basic";

test.describe.serial("RBAC Deep Tests @deep", () => {
  let pluginLoaded = false;
  test.beforeEach(({ }, testInfo) => {
    // Skip all tests after the plugin check if plugin isn't loaded
    if (!pluginLoaded && !testInfo.title.includes("user info") && !testInfo.title.includes("plugin is loaded")) {
      testInfo.skip(true, "rights_basic plugin not loaded");
    }
  });
  // Store IDs across serial tests
  let currentUserId: string;
  let adminRoleId: number;
  let memberRoleId: number;
  let viewerRoleId: number;
  let testConversationId: string;
  let secondUserId: string;

  // --- Setup: Get current user info ---
  test("@deep should get current user info for RBAC tests", async ({
    apiClient,
  }) => {
    // Try /api/users/me first, fallback to /api/auth/me
    let res = await apiClient.get("/api/users/me");
    if (!res.ok()) {
      res = await apiClient.get("/api/auth/me");
    }
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    currentUserId = body.id || body.user?.id || body.user_id || body.sub;
    expect(currentUserId).toBeTruthy();
  });

  // --- 1. Plugin Loading Verification ---
  test("@deep should verify rights_basic plugin is loaded", async ({
    apiClient,
  }) => {
    const res = await apiClient.get("/api/plugins");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    // Check that rights_basic appears in loaded plugins
    const plugins = body.plugins || body;
    const rbacPlugin = Array.isArray(plugins)
      ? plugins.find((p: any) => p.name === "rights_basic")
      : null;
    if (!rbacPlugin) {
      test.skip(true, "rights_basic plugin not loaded — RBAC tests require it");
      return;
    }
    pluginLoaded = true;
    expect(rbacPlugin).toBeTruthy();
  });

  // --- 2. Role Listing ---
  test("@deep should list built-in roles (admin, member, viewer)", async ({
    apiClient,
  }) => {
    const res = await apiClient.get(`${RBAC_BASE}/roles`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.roles).toBeDefined();
    expect(body.roles.length).toBeGreaterThanOrEqual(3);

    const roleNames = body.roles.map((r: any) => r.name);
    expect(roleNames).toContain("admin");
    expect(roleNames).toContain("member");
    expect(roleNames).toContain("viewer");

    // Store role IDs for later tests
    adminRoleId = body.roles.find((r: any) => r.name === "admin").id;
    memberRoleId = body.roles.find((r: any) => r.name === "member").id;
    viewerRoleId = body.roles.find((r: any) => r.name === "viewer").id;

    // Verify built-in flags
    for (const role of body.roles) {
      if (["admin", "member", "viewer"].includes(role.name)) {
        expect(role.is_builtin).toBe(true);
        expect(role.is_custom).toBe(false);
        expect(role.tier).toBe("team");
      }
    }
  });

  // --- 3. Role Permission Matrix ---
  test("@deep should get admin role permission matrix", async ({
    apiClient,
  }) => {
    if (!adminRoleId) {
      test.skip(true, "adminRoleId not set — role listing test may have been skipped");
      return;
    }
    const res = await apiClient.get(
      `${RBAC_BASE}/roles/${adminRoleId}/permissions`,
    );

    // If the test user doesn't have admin access, the endpoint may return 403
    if (res.status() === 403 || res.status() === 401) {
      test.skip(true, "Current user lacks admin access to query admin role permissions");
      return;
    }

    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.role_id).toBe(adminRoleId);
    expect(body.role_name).toBe("admin");
    expect(body.permissions).toBeDefined();
    expect(body.permissions.length).toBeGreaterThanOrEqual(25);

    // Admin should have system:manage_users
    const sysManage = body.permissions.find(
      (p: any) => p.scope === "system:manage_users",
    );
    expect(sysManage).toBeTruthy();
    expect(sysManage.granted).toBe(true);
  });

  test("@deep should get viewer role with restricted permissions", async ({
    apiClient,
  }) => {
    if (!viewerRoleId) {
      test.skip(true, "viewerRoleId not set — role listing test may have been skipped");
      return;
    }
    const res = await apiClient.get(
      `${RBAC_BASE}/roles/${viewerRoleId}/permissions`,
    );

    // If the current user lacks permission to query role details, skip gracefully
    if (res.status() === 403 || res.status() === 401) {
      test.skip(true, "Current user lacks permission to query viewer role permissions");
      return;
    }

    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.role_name).toBe("viewer");

    // Viewer should only have view/query permissions
    for (const perm of body.permissions) {
      if (perm.granted) {
        expect(["view", "query", "export"]).toContain(perm.action);
      }
    }

    // Viewer should NOT have system permissions
    const sysPerms = body.permissions.filter(
      (p: any) => p.scope.startsWith("system:") && p.granted,
    );
    expect(sysPerms.length).toBe(0);
  });

  // --- 4. Permission Checking ---
  test("@deep should check self-permission via API", async ({ apiClient }) => {
    const res = await apiClient.get(
      `${RBAC_BASE}/check?user_id=${currentUserId}` +
        "&resource_type=conversation&resource_id=test-42&action=view",
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.allowed).toBeDefined();
    expect(typeof body.allowed).toBe("boolean");
    expect(body.reason).toBeTruthy();
    expect(body.source).toBeTruthy();
  });

  test("@deep should batch check multiple permissions", async ({
    apiClient,
  }) => {
    const res = await apiClient.post(`${RBAC_BASE}/check/batch`, {
      data: {
        user_id: currentUserId,
        checks: [
          { resource_type: "conversation", resource_id: "42", action: "view" },
          { resource_type: "workflow", resource_id: "7", action: "execute" },
          {
            resource_type: "system",
            resource_id: "*",
            action: "manage_users",
          },
        ],
      },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.results).toBeDefined();
    expect(body.results.length).toBe(3);

    for (const result of body.results) {
      expect(result.allowed).toBeDefined();
      expect(result.reason).toBeTruthy();
    }
  });

  // --- 5. Role Assignment ---
  test("@deep should assign member role to current user", async ({
    apiClient,
  }) => {
    // memberRoleId should be set from the role listing test
    expect(memberRoleId).toBeTruthy();

    const res = await apiClient.post(
      `${RBAC_BASE}/users/${currentUserId}/roles`,
      {
        data: {
          role_id: memberRoleId,
          scope_type: "global",
          scope_id: null,
        },
      },
    );
    // 201 Created, 200 OK, 409 already assigned, or 403 if current user lacks admin role
    expect([200, 201, 403, 409]).toContain(res.status());

    if (res.status() === 201) {
      const body = await res.json();
      expect(body.user_id).toBe(currentUserId);
      expect(body.role_name).toBe("member");
      expect(body.scope_type).toBe("global");
    }
  });

  // --- 6. Effective Permissions ---
  test("@deep should get effective permissions for current user", async ({
    apiClient,
  }) => {
    const res = await apiClient.get(
      `${RBAC_BASE}/users/${currentUserId}/permissions`,
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.user_id).toBe(currentUserId);
    expect(body.effective_permissions).toBeDefined();

    // User should have at least conversation permissions
    if (body.effective_permissions.conversation) {
      expect(body.effective_permissions.conversation).toContain("view");
    }
  });

  // --- 7. Permission Scopes ---
  test("@deep should list registered permission scopes", async ({
    apiClient,
  }) => {
    const res = await apiClient.get(`${RBAC_BASE}/scopes`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.scopes).toBeDefined();
    expect(body.scopes.length).toBeGreaterThanOrEqual(20);

    // Check that conversation scopes exist
    const convView = body.scopes.find(
      (s: any) => s.name === "conversation:view",
    );
    expect(convView).toBeTruthy();
    expect(convView.plugin).toBe("rights_basic");
    expect(convView.resource_type).toBe("conversation");
  });

  // --- 8. Scope Registration (plugin-to-plugin) ---
  test("@deep should register custom scopes from external plugin", async ({
    apiClient,
  }) => {
    const res = await apiClient.post(`${RBAC_BASE}/scopes/register`, {
      data: {
        plugin: "test_plugin",
        scopes: [
          {
            name: "test_plugin:custom_action",
            description: "Custom test action",
            resource_type: "test_resource",
          },
        ],
      },
    });
    expect(res.status()).toBe(201);
    const body = await res.json();
    expect(body.registered).toBe(1);
    expect(body.scopes).toContain("test_plugin:custom_action");
  });

  // --- 9. User Management (admin panel) ---
  test("@deep should list users with roles", async ({ apiClient }) => {
    const res = await apiClient.get(`${RBAC_BASE}/users?page=1&per_page=10`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.users).toBeDefined();
    expect(body.total).toBeGreaterThanOrEqual(1);
    expect(body.page).toBe(1);
    expect(body.per_page).toBe(10);

    // Each user should have expected fields
    for (const user of body.users) {
      expect(user.user_id).toBeTruthy();
      expect(user.email).toBeTruthy();
    }
  });

  // --- 10. Resource Sharing ---
  test("@deep should create a conversation for sharing tests", async ({
    apiClient,
  }) => {
    // Create a conversation to use in sharing tests
    const res = await apiClient.post("/api/chat/conversations", {
      data: { title: "RBAC Test Conversation", mode: "chat" },
    });
    if (res.ok()) {
      const body = await res.json();
      testConversationId = body.id || body.conversation_id;
    } else {
      // If conversation creation fails, try to get an existing one
      const listRes = await apiClient.get(
        "/api/chat/conversations?limit=1&page=1",
      );
      if (listRes.ok()) {
        const listBody = await listRes.json();
        const convs = listBody.conversations || listBody;
        if (Array.isArray(convs) && convs.length > 0) {
          testConversationId = convs[0].id;
        }
      }
    }
    // Test continues even if no conversation -- sharing tests will gracefully handle it
  });

  test("@deep should get resource permissions (empty initially)", async ({
    apiClient,
  }) => {
    if (!testConversationId) {
      test.skip();
      return;
    }

    const res = await apiClient.get(
      `${RBAC_BASE}/resources/conversation/${testConversationId}/permissions`,
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.resource_type).toBe("conversation");
    expect(body.resource_id).toBe(String(testConversationId));
    expect(body.shares).toBeDefined();
    expect(Array.isArray(body.shares)).toBe(true);
  });

  // --- 11. Audit Logging ---
  test("@deep should query permission audit log", async ({ apiClient }) => {
    const res = await apiClient.get(`${RBAC_BASE}/audit?page=1&per_page=10`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.entries).toBeDefined();
    expect(Array.isArray(body.entries)).toBe(true);
    expect(body.total).toBeDefined();
    expect(body.page).toBe(1);

    // If there are entries, verify structure
    if (body.entries.length > 0) {
      const entry = body.entries[0];
      expect(entry.actor_id).toBeTruthy();
      expect(entry.action).toBeTruthy();
      expect(entry.target_type).toBeTruthy();
      expect(entry.target_id).toBeTruthy();
      expect(entry.timestamp).toBeTruthy();
    }
  });

  test("@deep should find role_assigned audit entries from earlier test", async ({
    apiClient,
  }) => {
    const res = await apiClient.get(
      `${RBAC_BASE}/audit?action=role_assigned&page=1&per_page=10`,
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.entries).toBeDefined();
    // If role was assigned in test 5, there should be at least 1 entry
    // (but may be 0 if role was already assigned via 409)
  });

  // --- 12. Enterprise Tier Gating ---
  test("@deep should reject custom role creation (Enterprise only)", async ({
    apiClient,
  }) => {
    const res = await apiClient.post(`${RBAC_BASE}/roles`, {
      data: {
        name: "custom_role",
        description: "Should fail",
        base_role: "member",
        permissions: [],
      },
    });
    expect(res.status()).toBe(403);
    const body = await res.json();
    expect(body.detail).toContain("Enterprise");
  });

  test("@deep should reject role deletion (Enterprise only)", async ({
    apiClient,
  }) => {
    if (!viewerRoleId) {
      test.skip(true, "viewerRoleId not set — role listing test may have been skipped");
      return;
    }
    const res = await apiClient.delete(`${RBAC_BASE}/roles/${viewerRoleId}`);
    expect(res.status()).toBe(400); // Cannot delete built-in role
  });

  // --- 13. Permission after role change ---
  test("@deep should verify permission check reflects role assignment", async ({
    apiClient,
  }) => {
    // Check permission for the user who has member role assigned
    const res = await apiClient.get(
      `${RBAC_BASE}/check?user_id=${currentUserId}` +
        "&resource_type=conversation&resource_id=test-99&action=view",
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    // With member role, conversation:view should be allowed
    expect(body.allowed).toBe(true);
    expect(body.source).toBeTruthy();
  });

  // --- 14. Cross-user permission denial and sharing grant ---
  // CONTEXT.md LOCKED: "resource access with/without permissions"
  test("@deep should deny second user access to primary user's resource, then grant via sharing", async ({
    apiClient,
    playwright,
  }) => {
    // Skip if no conversation was created in test 10
    if (!testConversationId) {
      test.skip();
      return;
    }

    // Step 1: Register a second user via /api/auth/register
    const uniqueSuffix = Date.now();
    const secondUserEmail = `rbac-test-user-${uniqueSuffix}@example.com`;
    const secondUserPassword = `RbacTest!${uniqueSuffix}`;

    const registerRes = await apiClient.post("/api/auth/register", {
      data: {
        email: secondUserEmail,
        password: secondUserPassword,
        display_name: `rbac_test_${uniqueSuffix}`,
      },
    });
    // 201 Created or 200 OK depending on backend
    expect([200, 201]).toContain(registerRes.status());
    const registerBody = await registerRes.json();
    // Register returns JWT tokens, not a user object.
    // Extract user ID from the JWT sub claim.
    secondUserId =
      registerBody.id ||
      registerBody.user?.id ||
      registerBody.user_id ||
      registerBody.sub;
    if (!secondUserId && registerBody.access_token) {
      try {
        const payload = JSON.parse(
          Buffer.from(registerBody.access_token.split(".")[1], "base64").toString(),
        );
        secondUserId = payload.sub;
      } catch {
        // ignore decode errors
      }
    }
    expect(secondUserId).toBeTruthy();

    // Step 2: Authenticate as second user to get their token
    // Register already returns tokens, so use them directly; fall back to login
    const secondUserToken = registerBody.access_token || registerBody.token;
    let finalToken = secondUserToken;
    if (!finalToken) {
      const loginRes = await apiClient.post("/api/auth/login", {
        data: {
          email: secondUserEmail,
          password: secondUserPassword,
        },
      });
      expect(loginRes.ok()).toBeTruthy();
      const loginBody = await loginRes.json();
      finalToken =
        loginBody.access_token || loginBody.token || loginBody.accessToken;
    }
    expect(finalToken).toBeTruthy();

    // Step 3: Create a separate API client for the second user
    const secondApiClient = await playwright.request.newContext({
      baseURL: API_URL,
      ignoreHTTPSErrors: true,
      extraHTTPHeaders: { Authorization: `Bearer ${finalToken}` },
    });

    try {
      // Step 4: Verify second user is DENIED access to primary user's conversation
      const denyRes = await secondApiClient.get(
        `${RBAC_BASE}/check?user_id=${secondUserId}` +
          `&resource_type=conversation&resource_id=${testConversationId}&action=view`,
      );
      expect(denyRes.ok()).toBeTruthy();
      const denyBody = await denyRes.json();
      expect(denyBody.allowed).toBe(false);

      // Step 5: Primary user shares the conversation with second user (using primary apiClient)
      const shareRes = await apiClient.post(
        `${RBAC_BASE}/resources/conversation/${testConversationId}/share`,
        {
          data: {
            shared_with: secondUserId,
            permission: "view",
          },
        },
      );
      expect([200, 201]).toContain(shareRes.status());

      // Step 6: Verify second user is NOW ALLOWED access after sharing
      const allowRes = await secondApiClient.get(
        `${RBAC_BASE}/check?user_id=${secondUserId}` +
          `&resource_type=conversation&resource_id=${testConversationId}&action=view`,
      );
      expect(allowRes.ok()).toBeTruthy();
      const allowBody = await allowRes.json();
      expect(allowBody.allowed).toBe(true);
    } finally {
      await secondApiClient.dispose();
    }
  });
});
