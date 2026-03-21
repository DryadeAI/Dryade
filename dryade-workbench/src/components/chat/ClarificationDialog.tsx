// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { HelpCircle, Send } from "lucide-react";

interface ClarificationOption {
  id: string;
  label: string;
  description?: string;
}

interface ClarificationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentName: string;
  question: string;
  options?: ClarificationOption[];
  allowFreeform?: boolean;
  onSubmit: (response: string) => void;
  onCancel?: () => void;
}

const ClarificationDialog = ({
  open,
  onOpenChange,
  agentName,
  question,
  options = [],
  allowFreeform = true,
  onSubmit,
  onCancel,
}: ClarificationDialogProps) => {
  const [selectedOption, setSelectedOption] = useState<string>("");
  const [freeformResponse, setFreeformResponse] = useState("");

  const handleSubmit = () => {
    const response = options.length > 0 ? selectedOption : freeformResponse;
    if (response.trim()) {
      onSubmit(response);
      onOpenChange(false);
      setSelectedOption("");
      setFreeformResponse("");
    }
  };

  const handleCancel = () => {
    onCancel?.();
    onOpenChange(false);
    setSelectedOption("");
    setFreeformResponse("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-primary" />
            Clarification Needed
          </DialogTitle>
          <DialogDescription>
            <span className="font-medium text-foreground">{agentName}</span> needs
            your input to proceed.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Question */}
          <div className="p-4 bg-muted/50 rounded-lg border border-border">
            <p className="text-sm text-foreground">{question}</p>
          </div>

          {/* Options (if provided) */}
          {options.length > 0 && (
            <div className="space-y-2">
              <Label>Select an option:</Label>
              <RadioGroup
                value={selectedOption}
                onValueChange={setSelectedOption}
                className="space-y-2"
              >
                {options.map((option) => (
                  <label
                    key={option.id}
                    className="flex items-start gap-3 p-3 rounded-lg border border-border hover:bg-muted/30 cursor-pointer transition-colors"
                  >
                    <RadioGroupItem value={option.id} className="mt-0.5" />
                    <div>
                      <p className="text-sm font-medium">{option.label}</p>
                      {option.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {option.description}
                        </p>
                      )}
                    </div>
                  </label>
                ))}
              </RadioGroup>
            </div>
          )}

          {/* Freeform input */}
          {allowFreeform && options.length === 0 && (
            <div className="space-y-2">
              <Label htmlFor="clarification-response">Your response:</Label>
              <Textarea
                id="clarification-response"
                value={freeformResponse}
                onChange={(e) => setFreeformResponse(e.target.value)}
                placeholder="Type your response..."
                className="min-h-24"
              />
            </div>
          )}

          {/* Allow freeform even with options */}
          {allowFreeform && options.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="other-response" className="text-muted-foreground">
                Or provide a different response:
              </Label>
              <Input
                id="other-response"
                value={freeformResponse}
                onChange={(e) => {
                  setFreeformResponse(e.target.value);
                  if (e.target.value) setSelectedOption("");
                }}
                placeholder="Type your own response..."
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              options.length > 0
                ? !selectedOption && !freeformResponse.trim()
                : !freeformResponse.trim()
            }
          >
            <Send className="w-4 h-4 mr-2" />
            Submit
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ClarificationDialog;
