// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

interface AuthGuardProps {
  children: ReactNode;
  requiredRole?: "admin" | "member";
  fallbackPath?: string;
}

const AuthGuard = ({
  children,
  requiredRole,
  fallbackPath = "/auth",
}: AuthGuardProps) => {
  const location = useLocation();
  const { isAuthenticated, isLoading, user } = useAuth();

  // While auth state is loading, render nothing to avoid flash
  if (isLoading) {
    return null;
  }

  // Check authentication - defaults to false (unauthenticated)
  if (!isAuthenticated) {
    return <Navigate to={fallbackPath} state={{ from: location }} replace />;
  }

  // Check role requirement
  const userRole = user?.role === "admin" ? "admin" : "member";
  if (requiredRole && requiredRole === "admin" && userRole !== "admin") {
    return <Navigate to="/403" replace />;
  }

  return <>{children}</>;
};

export default AuthGuard;
