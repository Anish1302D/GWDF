import en from "./en.json";
import hi from "./hi.json";
import mr from "./mr.json";

export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिन्दी" },
  { code: "mr", label: "मराठी" },
];

const DICTIONARIES = { en, hi, mr };

export function getDictionary(lang) {
  return DICTIONARIES[lang] || DICTIONARIES.en;
}
