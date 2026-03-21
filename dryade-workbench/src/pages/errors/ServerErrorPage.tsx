// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ChevronDown, ChevronUp, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import ErrorLayout from "@/components/errors/ErrorLayout";
import { toast } from "sonner";

const ServerErrorPage = () => {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [description, setDescription] = useState("");

  const errorId = `ERR-${Date.now().toString(36).toUpperCase()}`;
  const timestamp = new Date().toISOString();

  const handleCopyErrorId = () => {
    navigator.clipboard.writeText(errorId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleReportSubmit = () => {
    toast.success("Report Submitted", { description: "Thank you for your feedback. Our team will investigate." });
  };

  const handleRetry = () => {
    window.location.reload();
  };

  return (
    <ErrorLayout>
      <Card className="border-border/50">
        <CardContent className="pt-8 pb-8 space-y-6">
          <div className="w-16 h-16 mx-auto rounded-full bg-destructive/10 flex items-center justify-center">
            <AlertTriangle className="w-8 h-8 text-destructive" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-semibold text-foreground">Something Went Wrong</h1>
            <p className="text-muted-foreground">
              We're having trouble processing your request.
            </p>
            <p className="text-sm text-muted-foreground">
              Our team has been notified. Please try again later.
            </p>
          </div>

          <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
            <CollapsibleTrigger asChild>
              <button className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mx-auto">
                Error details
                {detailsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-4">
              <div className="bg-muted/50 rounded-lg p-4 text-left text-sm space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-muted-foreground">
                    <span className="font-medium">Error ID:</span> {errorId}
                  </p>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={handleCopyErrorId}
                  >
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                  </Button>
                </div>
                <p className="text-muted-foreground">
                  <span className="font-medium">Timestamp:</span> {timestamp}
                </p>
              </div>
            </CollapsibleContent>
          </Collapsible>

          <div className="flex flex-col gap-3">
            <Button size="lg" className="w-full" onClick={handleRetry}>
              Try Again
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" size="lg" className="w-full">
                  Report Issue
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Report Issue</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="bg-muted/50 rounded-lg p-3 text-sm">
                    <span className="font-medium">Error ID:</span> {errorId}
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">
                      Optional Description
                    </label>
                    <Textarea
                      placeholder="What were you doing when this happened?"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={4}
                    />
                  </div>
                  <Button className="w-full" onClick={handleReportSubmit}>
                    Submit Report
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
            <Button asChild variant="ghost" size="lg" className="w-full">
              <Link to="/workspace/dashboard">Go to Dashboard</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </ErrorLayout>
  );
};

export default ServerErrorPage;
