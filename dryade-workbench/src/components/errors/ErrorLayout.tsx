// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link } from "react-router-dom";

interface ErrorLayoutProps {
  children: React.ReactNode;
}

const ErrorLayout = ({ children }: ErrorLayoutProps) => {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Minimal Header */}
      <header className="p-4 border-b border-border">
        <Link to="/" className="flex items-center gap-2 w-fit">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-sm">D</span>
          </div>
          <span className="font-semibold text-foreground">
            Dryade<span className="text-primary">App</span>
          </span>
        </Link>
      </header>

      {/* Centered Content */}
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md text-center space-y-6">
          {children}
        </div>
      </main>
    </div>
  );
};

export default ErrorLayout;
