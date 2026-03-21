// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { MessageSquare, Workflow, ClipboardList, Upload } from "lucide-react";

const QuickActions = () => {
  const { t } = useTranslation('dashboard');

  const actions = [
    {
      labelKey: "quickActions.newChat",
      descKey: "quickActions.newChatDesc",
      href: "/workspace/chat",
      icon: MessageSquare,
      variant: "default" as const,
      primary: true,
    },
    {
      labelKey: "quickActions.createWorkflow",
      descKey: "quickActions.createWorkflowDesc",
      href: "/workspace/workflow",
      icon: Workflow,
      variant: "outline" as const,
    },
    {
      labelKey: "quickActions.newPlan",
      descKey: "quickActions.newPlanDesc",
      href: "/workspace/chat?mode=planner",
      icon: ClipboardList,
      variant: "outline" as const,
    },
    {
      labelKey: "quickActions.upload",
      descKey: "quickActions.uploadDesc",
      href: "/workspace/knowledge",
      icon: Upload,
      variant: "outline" as const,
    },
  ];

  return (
    <div className="glass-card p-5">
      <h2 className="text-lg font-semibold text-foreground mb-4">{t('sections.quickAccess')}</h2>
      <div className="grid grid-cols-2 gap-3">
        {actions.map((action) => (
          <Button
            key={action.labelKey}
            variant={action.variant}
            className={
              action.primary
                ? "h-auto py-3 flex-col gap-1 bg-gradient-to-r from-primary to-accent hover:opacity-90"
                : "h-auto py-3 flex-col gap-1"
            }
            asChild
          >
            <Link to={action.href}>
              <action.icon size={20} />
              <span className="font-medium">{t(action.labelKey)}</span>
              <span className="text-xs opacity-70">{t(action.descKey)}</span>
            </Link>
          </Button>
        ))}
      </div>
    </div>
  );
};

export default QuickActions;
