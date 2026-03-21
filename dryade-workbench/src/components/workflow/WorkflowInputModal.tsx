// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { WorkflowInputForm } from "./WorkflowInputForm";
import type { ScenarioInputSchema } from "@/types/extended-api";
import { Play } from "lucide-react";

interface WorkflowInputModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowName: string;
  inputs: ScenarioInputSchema[];
  onSubmit: (values: Record<string, unknown>, files: Record<string, File>) => void;
  isLoading?: boolean;
}

export const WorkflowInputModal = ({
  open,
  onOpenChange,
  workflowName,
  inputs,
  onSubmit,
  isLoading = false,
}: WorkflowInputModalProps) => {
  const handleSubmit = (values: Record<string, unknown>, files: Record<string, File>) => {
    onSubmit(values, files);
  };

  const handleCancel = () => {
    onOpenChange(false);
  };

  const requiredCount = inputs.filter((i) => i.required).length;
  const optionalCount = inputs.length - requiredCount;

  const formatWorkflowName = (name: string) => {
    return name
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[400px] sm:w-[450px]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Play size={18} className="text-primary" />
            Run {formatWorkflowName(workflowName)}
          </SheetTitle>
          <SheetDescription>
            {inputs.length === 0 ? (
              "Click Run to execute this workflow."
            ) : (
              <>
                {requiredCount > 0 &&
                  `${requiredCount} required input${requiredCount > 1 ? "s" : ""}`}
                {requiredCount > 0 && optionalCount > 0 && ", "}
                {optionalCount > 0 && `${optionalCount} optional`}
              </>
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6">
          <WorkflowInputForm
            inputs={inputs}
            onSubmit={handleSubmit}
            onCancel={handleCancel}
            isLoading={isLoading}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default WorkflowInputModal;
