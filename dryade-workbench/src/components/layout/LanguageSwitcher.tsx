// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { supportedLanguages } from '@/i18n';
import { cn } from '@/lib/utils';

interface LanguageSwitcherProps {
  collapsed?: boolean;
}

const LanguageSwitcher = ({ collapsed = false }: LanguageSwitcherProps) => {
  const { i18n } = useTranslation();
  const currentLang = supportedLanguages.find((l) => l.code === i18n.language) ?? supportedLanguages[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={collapsed ? 'icon' : 'sm'}
          className={cn(
            'text-muted-foreground hover:text-foreground',
            collapsed ? 'h-8 w-8' : 'h-8 gap-2 px-2'
          )}
        >
          <Globe size={16} />
          {!collapsed && (
            <span className="text-xs truncate max-w-[80px]">{currentLang.label}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[160px]">
        {supportedLanguages.map((lang) => (
          <DropdownMenuItem
            key={lang.code}
            onClick={() => i18n.changeLanguage(lang.code)}
            className={cn(
              'cursor-pointer',
              i18n.language === lang.code && 'bg-primary/10 text-primary font-medium'
            )}
          >
            {lang.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default LanguageSwitcher;
