// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// i18next configuration — side-effect import in main.tsx
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// EN
import enCommon from './locales/en/common.json';
import enAuth from './locales/en/auth.json';
import enSettings from './locales/en/settings.json';
import enDashboard from './locales/en/dashboard.json';
import enChat from './locales/en/chat.json';
import enAgents from './locales/en/agents.json';
import enWorkflows from './locales/en/workflows.json';
import enKnowledge from './locales/en/knowledge.json';
import enHealth from './locales/en/health.json';
import enMetrics from './locales/en/metrics.json';
import enAudit from './locales/en/audit.json';
import enFactory from './locales/en/factory.json';
import enPlugins from './locales/en/plugins.json';
import enAdmin from './locales/en/admin.json';
// FR
import frCommon from './locales/fr/common.json';
import frAuth from './locales/fr/auth.json';
import frSettings from './locales/fr/settings.json';
import frDashboard from './locales/fr/dashboard.json';
import frChat from './locales/fr/chat.json';
import frAgents from './locales/fr/agents.json';
import frWorkflows from './locales/fr/workflows.json';
import frKnowledge from './locales/fr/knowledge.json';
import frHealth from './locales/fr/health.json';
import frMetrics from './locales/fr/metrics.json';
import frAudit from './locales/fr/audit.json';
import frFactory from './locales/fr/factory.json';
import frPlugins from './locales/fr/plugins.json';
// ES
import esCommon from './locales/es/common.json';
import esAuth from './locales/es/auth.json';
import esSettings from './locales/es/settings.json';
import esDashboard from './locales/es/dashboard.json';
import esChat from './locales/es/chat.json';
import esAgents from './locales/es/agents.json';
import esWorkflows from './locales/es/workflows.json';
import esKnowledge from './locales/es/knowledge.json';
import esHealth from './locales/es/health.json';
import esMetrics from './locales/es/metrics.json';
import esAudit from './locales/es/audit.json';
import esFactory from './locales/es/factory.json';
import esPlugins from './locales/es/plugins.json';
// DE
import deCommon from './locales/de/common.json';
import deAuth from './locales/de/auth.json';
import deSettings from './locales/de/settings.json';
import deDashboard from './locales/de/dashboard.json';
import deChat from './locales/de/chat.json';
import deAgents from './locales/de/agents.json';
import deWorkflows from './locales/de/workflows.json';
import deKnowledge from './locales/de/knowledge.json';
import deHealth from './locales/de/health.json';
import deMetrics from './locales/de/metrics.json';
import deAudit from './locales/de/audit.json';
import deFactory from './locales/de/factory.json';
import dePlugins from './locales/de/plugins.json';
// IT
import itCommon from './locales/it/common.json';
import itAuth from './locales/it/auth.json';
import itSettings from './locales/it/settings.json';
import itDashboard from './locales/it/dashboard.json';
import itChat from './locales/it/chat.json';
import itAgents from './locales/it/agents.json';
import itWorkflows from './locales/it/workflows.json';
import itKnowledge from './locales/it/knowledge.json';
import itHealth from './locales/it/health.json';
import itMetrics from './locales/it/metrics.json';
import itAudit from './locales/it/audit.json';
import itFactory from './locales/it/factory.json';
import itPlugins from './locales/it/plugins.json';
// PT-BR
import ptBRCommon from './locales/pt-BR/common.json';
import ptBRAuth from './locales/pt-BR/auth.json';
import ptBRSettings from './locales/pt-BR/settings.json';
import ptBRDashboard from './locales/pt-BR/dashboard.json';
import ptBRChat from './locales/pt-BR/chat.json';
import ptBRAgents from './locales/pt-BR/agents.json';
import ptBRWorkflows from './locales/pt-BR/workflows.json';
import ptBRKnowledge from './locales/pt-BR/knowledge.json';
import ptBRHealth from './locales/pt-BR/health.json';
import ptBRMetrics from './locales/pt-BR/metrics.json';
import ptBRAudit from './locales/pt-BR/audit.json';
import ptBRFactory from './locales/pt-BR/factory.json';
import ptBRPlugins from './locales/pt-BR/plugins.json';
// ZH-CN
import zhCNCommon from './locales/zh-CN/common.json';
import zhCNAuth from './locales/zh-CN/auth.json';
import zhCNSettings from './locales/zh-CN/settings.json';
import zhCNDashboard from './locales/zh-CN/dashboard.json';
import zhCNChat from './locales/zh-CN/chat.json';
import zhCNAgents from './locales/zh-CN/agents.json';
import zhCNWorkflows from './locales/zh-CN/workflows.json';
import zhCNKnowledge from './locales/zh-CN/knowledge.json';
import zhCNHealth from './locales/zh-CN/health.json';
import zhCNMetrics from './locales/zh-CN/metrics.json';
import zhCNAudit from './locales/zh-CN/audit.json';
import zhCNFactory from './locales/zh-CN/factory.json';
import zhCNPlugins from './locales/zh-CN/plugins.json';
// JA
import jaCommon from './locales/ja/common.json';
import jaAuth from './locales/ja/auth.json';
import jaSettings from './locales/ja/settings.json';
import jaDashboard from './locales/ja/dashboard.json';
import jaChat from './locales/ja/chat.json';
import jaAgents from './locales/ja/agents.json';
import jaWorkflows from './locales/ja/workflows.json';
import jaKnowledge from './locales/ja/knowledge.json';
import jaHealth from './locales/ja/health.json';
import jaMetrics from './locales/ja/metrics.json';
import jaAudit from './locales/ja/audit.json';
import jaFactory from './locales/ja/factory.json';
import jaPlugins from './locales/ja/plugins.json';
// KO
import koCommon from './locales/ko/common.json';
import koAuth from './locales/ko/auth.json';
import koSettings from './locales/ko/settings.json';
import koDashboard from './locales/ko/dashboard.json';
import koChat from './locales/ko/chat.json';
import koAgents from './locales/ko/agents.json';
import koWorkflows from './locales/ko/workflows.json';
import koKnowledge from './locales/ko/knowledge.json';
import koHealth from './locales/ko/health.json';
import koMetrics from './locales/ko/metrics.json';
import koAudit from './locales/ko/audit.json';
import koFactory from './locales/ko/factory.json';
import koPlugins from './locales/ko/plugins.json';
// AR
import arCommon from './locales/ar/common.json';
import arAuth from './locales/ar/auth.json';
import arSettings from './locales/ar/settings.json';
import arDashboard from './locales/ar/dashboard.json';
import arChat from './locales/ar/chat.json';
import arAgents from './locales/ar/agents.json';
import arWorkflows from './locales/ar/workflows.json';
import arKnowledge from './locales/ar/knowledge.json';
import arHealth from './locales/ar/health.json';
import arMetrics from './locales/ar/metrics.json';
import arAudit from './locales/ar/audit.json';
import arFactory from './locales/ar/factory.json';
import arPlugins from './locales/ar/plugins.json';

export const supportedLanguages = [
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'es', label: 'Español' },
  { code: 'de', label: 'Deutsch' },
  { code: 'it', label: 'Italiano' },
  { code: 'pt-BR', label: 'Português (BR)' },
  { code: 'zh-CN', label: '简体中文' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'ar', label: 'العربية' },
] as const;

export const rtlLanguages = ['ar'];

const resources = {
  en: { common: enCommon, auth: enAuth, settings: enSettings, dashboard: enDashboard, chat: enChat, agents: enAgents, workflows: enWorkflows, knowledge: enKnowledge, health: enHealth, metrics: enMetrics, audit: enAudit, factory: enFactory, plugins: enPlugins, admin: enAdmin },
  fr: { common: frCommon, auth: frAuth, settings: frSettings, dashboard: frDashboard, chat: frChat, agents: frAgents, workflows: frWorkflows, knowledge: frKnowledge, health: frHealth, metrics: frMetrics, audit: frAudit, factory: frFactory, plugins: frPlugins },
  es: { common: esCommon, auth: esAuth, settings: esSettings, dashboard: esDashboard, chat: esChat, agents: esAgents, workflows: esWorkflows, knowledge: esKnowledge, health: esHealth, metrics: esMetrics, audit: esAudit, factory: esFactory, plugins: esPlugins },
  de: { common: deCommon, auth: deAuth, settings: deSettings, dashboard: deDashboard, chat: deChat, agents: deAgents, workflows: deWorkflows, knowledge: deKnowledge, health: deHealth, metrics: deMetrics, audit: deAudit, factory: deFactory, plugins: dePlugins },
  it: { common: itCommon, auth: itAuth, settings: itSettings, dashboard: itDashboard, chat: itChat, agents: itAgents, workflows: itWorkflows, knowledge: itKnowledge, health: itHealth, metrics: itMetrics, audit: itAudit, factory: itFactory, plugins: itPlugins },
  'pt-BR': { common: ptBRCommon, auth: ptBRAuth, settings: ptBRSettings, dashboard: ptBRDashboard, chat: ptBRChat, agents: ptBRAgents, workflows: ptBRWorkflows, knowledge: ptBRKnowledge, health: ptBRHealth, metrics: ptBRMetrics, audit: ptBRAudit, factory: ptBRFactory, plugins: ptBRPlugins },
  'zh-CN': { common: zhCNCommon, auth: zhCNAuth, settings: zhCNSettings, dashboard: zhCNDashboard, chat: zhCNChat, agents: zhCNAgents, workflows: zhCNWorkflows, knowledge: zhCNKnowledge, health: zhCNHealth, metrics: zhCNMetrics, audit: zhCNAudit, factory: zhCNFactory, plugins: zhCNPlugins },
  ja: { common: jaCommon, auth: jaAuth, settings: jaSettings, dashboard: jaDashboard, chat: jaChat, agents: jaAgents, workflows: jaWorkflows, knowledge: jaKnowledge, health: jaHealth, metrics: jaMetrics, audit: jaAudit, factory: jaFactory, plugins: jaPlugins },
  ko: { common: koCommon, auth: koAuth, settings: koSettings, dashboard: koDashboard, chat: koChat, agents: koAgents, workflows: koWorkflows, knowledge: koKnowledge, health: koHealth, metrics: koMetrics, audit: koAudit, factory: koFactory, plugins: koPlugins },
  ar: { common: arCommon, auth: arAuth, settings: arSettings, dashboard: arDashboard, chat: arChat, agents: arAgents, workflows: arWorkflows, knowledge: arKnowledge, health: arHealth, metrics: arMetrics, audit: arAudit, factory: arFactory, plugins: arPlugins },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: ['common', 'auth', 'settings', 'dashboard', 'chat', 'agents', 'workflows', 'knowledge', 'health', 'metrics', 'audit', 'factory', 'plugins', 'admin'],
    supportedLngs: supportedLanguages.map((l) => l.code),
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'i18nextLng',
      caches: ['localStorage'],
    },
    saveMissing: import.meta.env.DEV,
    missingKeyHandler: import.meta.env.DEV
      ? (_lngs: readonly string[], ns: string, key: string) => {
          console.warn(`[i18n] Missing key: ${ns}:${key}`);
        }
      : undefined,
  });

export default i18n;
