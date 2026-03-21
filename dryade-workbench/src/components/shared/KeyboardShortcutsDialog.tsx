// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Keyboard } from "lucide-react";
import { useTranslation } from "react-i18next";

interface ShortcutGroup {
  label: string;
  shortcuts: { keys: string[]; actionKey: string }[];
}

const shortcutGroups: ShortcutGroup[] = [
  {
    label: "shortcuts.groups.global",
    shortcuts: [
      { keys: ["\u2318", "K"], actionKey: "shortcuts.actions.commandPalette" },
      { keys: ["\u2318", "/"], actionKey: "shortcuts.actions.showKeyboardShortcuts" },
      { keys: ["\u2318", "\\"], actionKey: "shortcuts.actions.toggleSidebar" },
    ],
  },
  {
    label: "shortcuts.groups.chat",
    shortcuts: [
      { keys: ["\u2318", "F"], actionKey: "shortcuts.actions.searchMessages" },
      { keys: ["Enter"], actionKey: "shortcuts.actions.sendMessage" },
      { keys: ["Shift", "Enter"], actionKey: "shortcuts.actions.newLine" },
    ],
  },
  {
    label: "shortcuts.groups.workflow",
    shortcuts: [
      { keys: ["\u2318", "Enter"], actionKey: "shortcuts.actions.runWorkflow" },
      { keys: ["Escape"], actionKey: "shortcuts.actions.stopDeselect" },
      { keys: ["\u2318", "S"], actionKey: "shortcuts.actions.saveWorkflow" },
      { keys: ["\u2318", "Z"], actionKey: "shortcuts.actions.undo" },
      { keys: ["\u2318", "\u21e7", "Z"], actionKey: "shortcuts.actions.redo" },
      { keys: ["\u2318", "A"], actionKey: "shortcuts.actions.selectAllNodes" },
      { keys: ["\u2318", "C"], actionKey: "shortcuts.actions.copySelectedNodes" },
      { keys: ["\u2318", "V"], actionKey: "shortcuts.actions.pasteNodes" },
      { keys: ["\u2318", "D"], actionKey: "shortcuts.actions.duplicateNodes" },
      { keys: ["\u2318", "0"], actionKey: "shortcuts.actions.resetZoom" },
      { keys: ["\u2318", "1"], actionKey: "shortcuts.actions.fitView" },
      { keys: ["Delete"], actionKey: "shortcuts.actions.deleteSelected" },
    ],
  },
];

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const KeyBadge = ({ children }: { children: React.ReactNode }) => (
  <kbd className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 text-xs font-medium bg-muted border border-border rounded shadow-sm">
    {children}
  </kbd>
);

const KeyboardShortcutsDialog = ({
  open,
  onOpenChange,
}: KeyboardShortcutsDialogProps) => {
  const { t } = useTranslation('plugins');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" aria-label="Keyboard Shortcuts">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Keyboard className="w-5 h-5" aria-hidden="true" />
            {t('shortcuts.title')}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-6 py-4">
          {shortcutGroups.map((group) => (
            <div key={group.label}>
              <h3 className="text-sm font-medium text-muted-foreground mb-3">
                {t(group.label)}
              </h3>
              <div className="space-y-2">
                {group.shortcuts.map((shortcut, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between py-1.5"
                  >
                    <span className="text-sm text-foreground">
                      {t(shortcut.actionKey)}
                    </span>
                    <div className="flex items-center gap-1">
                      {shortcut.keys.map((key, keyIdx) => (
                        <KeyBadge key={keyIdx}>{key}</KeyBadge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground text-center">
          {t('shortcuts.toggleHintPrefix')} <KeyBadge>{'\u2318'}</KeyBadge> <KeyBadge>/</KeyBadge> {t('shortcuts.toggleHintSuffix')}
        </p>
      </DialogContent>
    </Dialog>
  );
};

export default KeyboardShortcutsDialog;
