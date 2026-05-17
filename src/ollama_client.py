import ollama
import os
import time
from dotenv import load_dotenv

load_dotenv(override=True)

from tools.logger import logger

# System prompt para RAG técnico de código
_SYSTEM_PROMPT_CODE = """Você é um assistente técnico especializado nos projetos Rust Star (engine MMORPG em Rust), FoxOT (servidor Tibia em C++) e FoxClient (cliente Tibia).

Ao responder:
1. USE o contexto fornecido como fonte primária. Cite o arquivo de origem quando relevante (ex: "Em `server/src/game_loop.rs`:").
2. Se o contexto não for suficiente, diga claramente: "A base de conhecimento indexada não contém essa informação."
3. Para código, mostre trechos relevantes do contexto quando útil.
4. Prefira respostas precisas e técnicas a respostas longas e genéricas.
5. Se a pergunta envolver múltiplos projetos, organize a resposta por projeto.
"""

_SYSTEM_PROMPT_VISION = """Você é um analisador técnico visual especializado em engines de jogo MMORPG.
Ao analisar a imagem:
1. Extraia TODOS os textos visíveis (código, mensagens de erro, logs, valores de variáveis).
2. Identifique o tipo de conteúdo: erro de compilação, bug de renderização, estado de jogo, diagrama de arquitetura, etc.
3. Descreva o contexto técnico: o que está acontecendo, qual sistema está envolvido.
4. Se for um erro, identifique a causa provável e o arquivo/função responsável.
5. Seja específico e técnico. Evite descrições vagas.
"""


class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:4b")
        self.rag_model = os.getenv("RAG_MODEL", "qwen3.5:4b")
        # Janela de contexto calibrada: 12k tokens (~5.9GB VRAM footprint para Qwen 4b)
        self.num_ctx = 12288

        try:
            self.client = ollama.Client(host=self.base_url)
            logger.info(
                f"OllamaClient conectado. Modelos: {self.embedding_model}, {self.rag_model} | Contexto: {self.num_ctx}"
            )
        except Exception as e:
            logger.critical(f"Falha ao instanciar OllamaClient ({self.base_url}): {str(e)}")
            raise

    def get_embedding(self, text: str, auto_unload: bool = True) -> list:
        """Gera embedding vetorial para o texto com timeout de 60s e num_ctx fixo."""
        try:
            # timeout em segundos para evitar travamentos
            response = self.client.embeddings(
                model=self.embedding_model,
                prompt=text,
                options={"timeout": 60, "num_ctx": self.num_ctx}
            )
            if auto_unload:
                self._unload_model(self.embedding_model, is_chat=False)
            return response["embedding"]
        except Exception as e:
            logger.error(f"Erro ao gerar embedding: {str(e)}")
            raise

    def generate_response(self, question: str, context: str = "", project_id: str = None) -> str:
        """Gera resposta RAG com timeout de 90s e num_ctx fixo."""
        try:
            project_label = project_id if project_id else "Todos os Projetos"
            user_content = f"[Escopo da Consulta: {project_label}]\n\n"

            if context.strip():
                user_content += f"--- CONTEXTO RECUPERADO DA BASE DE CONHECIMENTO ---\n{context}\n--- FIM DO CONTEXTO ---\n\n"
            else:
                user_content += "[Nenhum contexto específico encontrado na base de conhecimento para esta pergunta.]\n\n"

            user_content += f"Pergunta: {question}"

            logger.debug(f"Enviando prompt RAG para {self.rag_model}")

            response = self.client.chat(
                model=self.rag_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT_CODE},
                    {"role": "user",   "content": user_content},
                ],
                options={"num_ctx": self.num_ctx, "timeout": 90},
            )

            self._unload_model(self.rag_model, is_chat=True)
            return response["message"]["content"]

        except Exception as e:
            logger.error(f"Erro ao gerar resposta RAG: {str(e)}")
            raise

    def check_connection(self) -> dict:
        """Verifica se o Ollama está acessível e os modelos estão disponíveis."""
        try:
            models = self.client.list()
            available_names = [m.model for m in models.models]
            status = {
                "connected": True,
                "embedding_model_ok": self.embedding_model in available_names,
                "rag_model_ok": self.rag_model in available_names,
                "available_models": available_names,
            }
            logger.info(f"Ollama conectado. Modelos disponíveis: {available_names}")
            return status
        except Exception as e:
            logger.warning(f"Ollama offline ou inacessível ({self.base_url}): {str(e)}")
            return {"connected": False, "error": str(e)}

    def get_gpu_usage(self) -> str:
        """Retorna uso atual de VRAM via nvidia-smi (apenas NVIDIA)."""
        try:
            import subprocess
            result = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                 "--format=csv,nounits,noheader"],
                encoding="utf-8",
                timeout=5,
            )
            used, total, util = result.strip().split(",")
            pct = round(int(used.strip()) / int(total.strip()) * 100, 1)
            return f"VRAM: {used.strip()}MB / {total.strip()}MB ({pct}%) | GPU: {util.strip()}%"
        except Exception:
            return "nvidia-smi não disponível (GPU não detectada ou driver não NVIDIA)."

    def unload_models(self) -> bool:
        """Descarrega ambos os modelos da VRAM imediatamente."""
        try:
            logger.info(f"Solicitando descarga de modelos da VRAM (Embedding: {self.embedding_model}, RAG: {self.rag_model})...")
            self._unload_model(self.embedding_model, is_chat=False)
            self._unload_model(self.rag_model, is_chat=True)
            logger.info("Comandos de descarga de modelos enviados com sucesso.")
            return True
        except Exception as e:
            logger.error(f"Erro ao descarregar modelos: {str(e)}")
            return False

    def describe_image(self, image_path: str) -> str:
        """Analisa imagem com Vision e retorna descrição técnica detalhada. Libera VRAM após uso."""
        try:
            import base64
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            logger.info(f"Processando imagem Vision: {image_path}")

            response = self.client.chat(
                model=self.rag_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT_VISION},
                    {
                        "role": "user",
                        "content": "Analise esta imagem e forneça um relatório técnico detalhado.",
                        "images": [b64],
                    },
                ],
                options={"num_ctx": self.num_ctx},
            )

            self._unload_model(self.rag_model, is_chat=True)
            return response["message"]["content"]

        except Exception as e:
            logger.error(f"Erro na análise Vision de {image_path}: {str(e)}")
            return ""

    def _unload_model(self, model_name: str, is_chat: bool) -> None:
        """Envia keep_alive=0 para liberar o modelo da VRAM imediatamente com timeout de 30s."""
        try:
            start_time = time.time()
            if is_chat:
                self.client.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": ""}],
                    keep_alive=0,
                    options={"num_ctx": 1, "timeout": 30}
                )
            else:
                self.client.generate(
                    model=model_name, 
                    prompt="", 
                    keep_alive=0,
                    options={"timeout": 30}
                )
            duration = time.time() - start_time
            logger.info(f"Modelo {model_name} descarregado em {duration:.2f}s (keep_alive=0 enviado).")
        except Exception as e:
            logger.debug(f"Aviso ao descarregar {model_name}: {str(e)}")
