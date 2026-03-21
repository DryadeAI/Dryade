// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { usePreferences } from "@/hooks/usePreferences";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sun, Moon, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

const ThemeToggle = () => {
  const { preferences, updatePreference, resolvedTheme } = usePreferences();

  const themes = [
    { value: "light" as const, label: "Light", icon: Sun },
    { value: "dark" as const, label: "Dark", icon: Moon },
    { value: "system" as const, label: "System", icon: Monitor },
  ];

  const currentTheme = themes.find((t) => t.value === preferences.theme);
  const CurrentIcon = resolvedTheme === "dark" ? Moon : Sun;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <CurrentIcon size={16} />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {themes.map((theme) => (
          <DropdownMenuItem
            key={theme.value}
            onClick={() => updatePreference("theme", theme.value)}
            className={cn(
              "gap-2",
              preferences.theme === theme.value && "bg-primary/10"
            )}
          >
            <theme.icon size={14} />
            {theme.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default ThemeToggle;
