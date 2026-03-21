// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ToggleWithConfirm - Toggle requiring confirmation for dangerous actions
// Based on COMPONENTS-4.md specification

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { AlertTriangle } from "lucide-react";

interface ToggleWithConfirmProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  confirmMessage: string;
  confirmTitle?: string;
  confirmAction?: string;
  cancelAction?: string;
  dangerous?: boolean;
  disabled?: boolean;
  className?: string;
}

const ToggleWithConfirm = ({
  checked,
  onChange,
  label,
  description,
  confirmMessage,
  confirmTitle = "Confirm Action",
  confirmAction = "Confirm",
  cancelAction = "Cancel",
  dangerous = false,
  disabled = false,
  className,
}: ToggleWithConfirmProps) => {
  const [showConfirm, setShowConfirm] = useState(false);
  const [pendingValue, setPendingValue] = useState<boolean | null>(null);

  const handleToggle = (newValue: boolean) => {
    // Only show confirmation when:
    // - For dangerous toggles: always confirm
    // - For non-dangerous toggles: confirm when turning OFF (disabling a feature)
    const shouldConfirm = dangerous ? true : !newValue;
    
    if (shouldConfirm) {
      setPendingValue(newValue);
      setShowConfirm(true);
    } else {
      onChange(newValue);
    }
  };

  const handleConfirm = () => {
    if (pendingValue !== null) {
      onChange(pendingValue);
    }
    setShowConfirm(false);
    setPendingValue(null);
  };

  const handleCancel = () => {
    setShowConfirm(false);
    setPendingValue(null);
  };

  return (
    <>
      <div
        className={cn(
          "flex items-center justify-between gap-4 p-3 rounded-lg transition-colors",
          dangerous ? "bg-destructive/5 hover:bg-destructive/10" : "bg-muted/30 hover:bg-muted/50",
          disabled && "opacity-50",
          className
        )}
      >
        <div className="flex items-start gap-3">
          {dangerous && (
            <AlertTriangle className="w-4 h-4 text-warning mt-0.5 flex-shrink-0" />
          )}
          <div>
            <Label
              htmlFor={`toggle-${label}`}
              className={cn(
                "text-sm font-medium cursor-pointer",
                disabled && "cursor-not-allowed"
              )}
            >
              {label}
            </Label>
            {description && (
              <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
            )}
          </div>
        </div>
        <Switch
          id={`toggle-${label}`}
          checked={checked}
          onCheckedChange={handleToggle}
          disabled={disabled}
          aria-describedby={description ? `${label}-description` : undefined}
        />
      </div>

      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              {dangerous && <AlertTriangle className="w-5 h-5 text-warning" />}
              {confirmTitle}
            </AlertDialogTitle>
            <AlertDialogDescription>{confirmMessage}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleCancel}>
              {cancelAction}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirm}
              className={cn(
                dangerous && "bg-destructive text-destructive-foreground hover:bg-destructive/90"
              )}
            >
              {confirmAction}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export default ToggleWithConfirm;
