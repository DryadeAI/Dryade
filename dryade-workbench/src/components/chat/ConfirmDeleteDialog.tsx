// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";
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
import { AlertTriangle } from "lucide-react";

interface ConfirmDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => Promise<void>;
  title: string;
  description: string;
  confirmText?: string;
  itemCount?: number;
}

export const ConfirmDeleteDialog = ({
  open,
  onOpenChange,
  onConfirm,
  title,
  description,
  confirmText = "DELETE ALL",
  itemCount,
}: ConfirmDeleteDialogProps) => {
  const [inputValue, setInputValue] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  // Reset input when dialog opens/closes
  useEffect(() => {
    if (!open) {
      setInputValue("");
    }
  }, [open]);

  const isConfirmed = inputValue === confirmText;

  const handleConfirm = async () => {
    if (!isConfirmed) return;

    setIsDeleting(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle size={20} />
            {title}
          </DialogTitle>
          <DialogDescription className="text-left">
            {description}
            {itemCount !== undefined && (
              <span className="block mt-2 font-medium text-foreground">
                This will permanently delete {itemCount} conversation{itemCount !== 1 ? "s" : ""}.
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="confirm-input">
            Type <span className="font-mono font-bold text-destructive">{confirmText}</span> to confirm
          </Label>
          <Input
            id="confirm-input"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={confirmText}
            autoComplete="off"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && isConfirmed) {
                handleConfirm();
              }
            }}
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={!isConfirmed || isDeleting}
          >
            {isDeleting ? "Deleting..." : "Delete Permanently"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ConfirmDeleteDialog;
