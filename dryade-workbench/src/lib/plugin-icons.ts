// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Shared Lucide icon map for plugin icon resolution.
 * Used by PluginsPage, IconChooser, and InstalledPluginCard.
 *
 * Each plugin's dryade.json manifest contains an "icon" field with a
 * PascalCase Lucide icon name. This map resolves those names to components.
 * The sidebar_item.icon field may use kebab-case (e.g. "graduation-cap").
 * resolvePluginIcon handles both formats.
 */
import {
  Activity, AlertTriangle, Award, BadgeCheck, BarChart3,
  Bell, BookOpen, Box, Boxes, Brain,
  Briefcase, Bug, Building2, Calculator, Car,
  Chrome, ClipboardCheck, ClipboardList, Cog, Cpu,
  Crosshair, Database, DollarSign, Edit, Eye,
  FileOutput, FileSearch, FileStack, FileText, FileWarning,
  FileLock, Flag, FlaskConical, Gauge, GitBranch,
  Globe, GraduationCap, Gavel, HardDrive, Headphones,
  Heart, HelpCircle, KanbanSquare, KeyRound, Landmark,
  Layers, LayoutTemplate, LifeBuoy, Lock, Map,
  Megaphone, MessageSquare, Mic, Microscope, Navigation,
  Network, PenTool, PieChart, Plug, Puzzle,
  Radio, Receipt, RefreshCw, RotateCcw, Scale,
  Scissors, Search, Server, Settings, Shield,
  ShieldAlert, ShieldCheck, Sparkles, Table, Target,
  TrendingUp, Truck, UserCheck, Users, Wifi,
  Workflow, Zap,
  type LucideIcon,
} from "lucide-react";

export const PLUGIN_ICON_MAP: Record<string, LucideIcon> = {
  Activity, AlertTriangle, Award, BadgeCheck, BarChart3,
  Bell, BookOpen, Box, Boxes, Brain,
  Briefcase, Bug, Building2, Calculator, Car,
  Chrome, ClipboardCheck, ClipboardList, Cog, Cpu,
  Crosshair, Database, DollarSign, Edit, Eye,
  FileOutput, FileSearch, FileStack, FileText, FileWarning,
  FileLock, Flag, FlaskConical, Gauge, GitBranch,
  Globe, GraduationCap, Gavel, HardDrive, Headphones,
  Heart, HelpCircle, KanbanSquare, KeyRound, Landmark,
  Layers, LayoutTemplate, LifeBuoy, Lock, Map,
  Megaphone, MessageSquare, Mic, Microscope, Navigation,
  Network, PenTool, PieChart, Plug, Puzzle,
  Radio, Receipt, RefreshCw, RotateCcw, Scale,
  Scissors, Search, Server, Settings, Shield,
  ShieldAlert, ShieldCheck, Sparkles, Table, Target,
  TrendingUp, Truck, UserCheck, Users, Wifi,
  Workflow, Zap,
};

/**
 * Lowercase lookup map built once from PLUGIN_ICON_MAP.
 * Supports kebab-case ("graduation-cap") and lowercase ("megaphone").
 */
const ICON_LOOKUP: Record<string, LucideIcon> = {};
for (const [name, icon] of Object.entries(PLUGIN_ICON_MAP)) {
  ICON_LOOKUP[name] = icon;                    // PascalCase: "GraduationCap"
  ICON_LOOKUP[name.toLowerCase()] = icon;      // lowercase:  "graduationcap"
  // kebab-case: "GraduationCap" -> "graduation-cap"
  const kebab = name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
  ICON_LOOKUP[kebab] = icon;
}

/** Resolve a Lucide icon name to a component, falling back to Puzzle.
 *  Accepts PascalCase ("Megaphone"), lowercase ("megaphone"), or kebab-case ("graduation-cap").
 */
export function resolvePluginIcon(iconName?: string | null): LucideIcon {
  if (!iconName) return Puzzle;
  return ICON_LOOKUP[iconName] ?? ICON_LOOKUP[iconName.toLowerCase()] ?? Puzzle;
}
