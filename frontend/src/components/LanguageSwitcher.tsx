import React from 'react';
import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';

/**
 * LanguageSwitcher Component
 * Allows switching between English ('en') and Hindi ('hi').
 *
 * NOTE: Hindi translations are machine-translated and require human review.
 * Reference: SIH26183, Phase 6 Specification.
 */
export const LanguageSwitcher: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { i18n } = useTranslation();

  const currentLang = i18n.language?.startsWith('hi') ? 'hi' : 'en';

  const toggleLanguage = () => {
    const nextLng = currentLang === 'hi' ? 'en' : 'hi';
    i18n.changeLanguage(nextLng);
  };

  return (
    <button
      type="button"
      onClick={toggleLanguage}
      aria-label={`Switch language. Current language: ${currentLang === 'hi' ? 'Hindi' : 'English'}`}
      title="Switch Language / भाषा बदलें (Hindi strings are machine-translated)"
      className={`px-2.5 py-1 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700 text-slate-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500 ${className}`}
    >
      <Globe className="w-3.5 h-3.5 text-blue-400" />
      <span className="font-bold tracking-wider">{currentLang === 'hi' ? 'हिं (HI)' : 'EN'}</span>
    </button>
  );
};
