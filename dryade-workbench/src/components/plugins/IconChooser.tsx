// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PLUGIN_ICON_MAP } from "@/lib/plugin-icons";

const ICON_ENTRIES = Object.entries(PLUGIN_ICON_MAP);

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface IconChooserProps {
  value?: string;
  onChange: (iconName: string) => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function IconChooser({ value, onChange, className }: IconChooserProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filtered = useMemo(() => {
    if (!searchQuery) return ICON_ENTRIES;
    const q = searchQuery.toLowerCase();
    return ICON_ENTRIES.filter(([name]) => name.toLowerCase().includes(q));
  }, [searchQuery]);

  const SelectedIcon = value ? PLUGIN_ICON_MAP[value] : null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn("gap-2 text-sm", className)}
        >
          {SelectedIcon ? (
            <>
              <SelectedIcon className="w-4 h-4" />
              <span>{value}</span>
            </>
          ) : (
            <span className="text-muted-foreground">Choose icon...</span>
          )}
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-80 p-3" align="start">
        <Input
          placeholder="Search icons..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="mb-3"
        />

        <div className="grid grid-cols-6 gap-2 max-h-64 overflow-y-auto">
          {filtered.map(([name, Icon]) => {
            const isSelected = value === name;
            return (
              <button
                key={name}
                type="button"
                title={name}
                className={cn(
                  "flex flex-col items-center justify-center p-2 rounded-md cursor-pointer transition-colors",
                  "hover:bg-accent",
                  isSelected && "ring-2 ring-primary bg-accent",
                )}
                onClick={() => {
                  onChange(name);
                  setOpen(false);
                }}
              >
                <Icon
                  className={cn(
                    "w-5 h-5",
                    isSelected ? "text-primary" : "text-muted-foreground",
                  )}
                />
                <span
                  className={cn(
                    "text-[10px] mt-1 truncate w-full text-center",
                    isSelected ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  {name}
                </span>
              </button>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">
            No icons match your search.
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
