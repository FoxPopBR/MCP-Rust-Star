import json
import os
import fnmatch
from tools.logger import logger

USER_PREFS_FILE = "data/user_preferences.json"
FACTORY_DEFAULTS_FILE = os.path.join(os.path.dirname(__file__), "resources/defaults.json")

class ConfigManager:
    def __init__(self):
        self.factory_defaults = self._load_json(FACTORY_DEFAULTS_FILE)
        self.user_prefs = self._load_json(USER_PREFS_FILE)
        self.current_settings = self._merge_configs(self.factory_defaults, self.user_prefs)
        self._gitignore_cache = {}

    def _load_json(self, path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Erro ao ler JSON em {path}: {e}")
        return {}

    def _merge_configs(self, base, overrides):
        """Realiza um deep merge simples para o esquema de dois níveis."""
        merged = base.copy()
        for key, value in overrides.items():
            if isinstance(value, dict) and key in merged:
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    def get_all(self):
        return self.current_settings

    def update(self, category: str, updates: dict):
        """Atualiza uma categoria específica de configurações."""
        if category not in self.user_prefs:
            self.user_prefs[category] = {}
        
        self.user_prefs[category].update(updates)
        self._save_user_prefs()
        self.current_settings = self._merge_configs(self.factory_defaults, self.user_prefs)
        logger.info(f"Preferências atualizadas na categoria: {category}")
        return self.current_settings

    def _save_user_prefs(self):
        try:
            os.makedirs(os.path.dirname(USER_PREFS_FILE), exist_ok=True)
            with open(USER_PREFS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.user_prefs, f, indent=4)
        except Exception as e:
            logger.error(f"Erro ao salvar user_preferences.json: {e}")

    def reset_to_defaults(self):
        if os.path.exists(USER_PREFS_FILE):
            os.remove(USER_PREFS_FILE)
        self.user_prefs = {}
        self.current_settings = self.factory_defaults.copy()
        logger.warning("Configurações resetadas para padrões de fábrica.")
        return self.current_settings

    def get_gitignore_patterns(self, project_root: str):
        if not project_root: return []
        if project_root in self._gitignore_cache:
            return self._gitignore_cache[project_root]
            
        gitignore_path = os.path.join(project_root, ".gitignore")
        patterns = []
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            except Exception as e:
                logger.error(f"Erro ao processar .gitignore em {project_root}: {e}")
        
        # Pré-processa os padrões para otimizar o fnmatch
        processed_patterns = []
        for p in patterns:
            processed_patterns.append((p, p.rstrip('/')))
            
        self._gitignore_cache[project_root] = processed_patterns
        return processed_patterns

    def is_ignored(self, file_path: str, project_root: str = None, ignore_ext_check: bool = False):
        settings = self.current_settings["indexing"]
        name = os.path.basename(file_path)
        is_dir = os.path.isdir(file_path)

        # 0. Filtro de Extensão (APENAS PARA ARQUIVOS)
        if not is_dir and not ignore_ext_check:
            ext = os.path.splitext(file_path)[1].lower()
            
            # Whitelist
            allowed_exts = settings.get("allowed_extensions", [])
            if allowed_exts and ext not in allowed_exts:
                return True

            # Blacklist (Fallback)
            if ext in settings.get("ignored_extensions", []):
                return True

        # 1. Filtro de Diretórios ignorados (verifica TODOS os componentes do path)
        ignored_dirs = set(settings.get("ignored_dirs", []))
        if ignored_dirs:
            parts = os.path.normpath(file_path).split(os.sep)
            for part in parts:
                if part in ignored_dirs:
                    return True

        # 3. Filtro .gitignore
        if settings.get("use_gitignore", True) and project_root:
            rel_path = os.path.relpath(file_path, project_root)
            patterns = self.get_gitignore_patterns(project_root)
            for pattern, clean_pattern in patterns:
                if (fnmatch.fnmatch(rel_path, pattern)
                        or fnmatch.fnmatch(name, pattern)
                        or rel_path.startswith(clean_pattern + os.sep)):
                    return True

        return False
