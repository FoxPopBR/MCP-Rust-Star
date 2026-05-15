import ollama
import os
from dotenv import load_dotenv

load_dotenv(override=True)

from tools.logger import logger

class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:4b")
        self.rag_model = os.getenv("RAG_MODEL", "qwen3.5:4b")
        # Ajuste estratégico de contexto: 12k tokens para otimizar footprint de VRAM (~1.5GB de economia)
        self.num_ctx = 12288
        
        try:
            self.client = ollama.Client(host=self.base_url)
            logger.info(f"OllamaClient inicializado para {self.base_url}. Contexto: {self.num_ctx}. Modelos: Embed={self.embedding_model}, RAG={self.rag_model}")
        except Exception as e:
            logger.critical(f"Falha ao conectar ao Ollama em {self.base_url}: {str(e)}")
            raise

    def get_embedding(self, text: str, auto_unload: bool = True):
        """Gera embedding. Se auto_unload=False, mantém o modelo na VRAM para o próximo uso."""
        try:
            response = self.client.embeddings(
                model=self.embedding_model, 
                prompt=text,
                options={"num_ctx": self.num_ctx}
            )
            if auto_unload:
                # Liberação agressiva apenas se solicitado (útil para chamadas únicas)
                self.client.generate(model=self.embedding_model, prompt='', keep_alive=0)
            return response['embedding']
        except Exception as e:
            logger.error(f"Erro ao gerar embedding: {str(e)}")
            raise

    def generate_response(self, prompt: str, context: str = "", project_id: str = None):
        """Gera uma resposta baseada em contexto e libera a VRAM imediatamente."""
        try:
            project_info = f"PROJETO: {project_id}\n" if project_id else "PROJETO: Contexto Global\n"
            full_prompt = project_info
            
            if context:
                full_prompt += f"Contexto Recuperado:\n{context}\n\n"
            
            full_prompt += f"Pergunta: {prompt}\n\nResposta baseada no contexto e projeto informados:"
            
            logger.debug(f"Enviando prompt para o modelo {self.rag_model} (Projeto: {project_id})")
            
            response = self.client.chat(
                model=self.rag_model, 
                messages=[{'role': 'user', 'content': full_prompt}],
                options={"num_ctx": self.num_ctx}
            )
            # Liberação agressiva de VRAM pós-uso (Hot Unload)
            self.client.chat(model=self.rag_model, messages=[], keep_alive=0)
            return response['message']['content']
        except Exception as e:
            logger.error(f"Erro ao gerar resposta do LLM: {str(e)}")
            raise

    def check_connection(self):
        """Verifica se o Ollama está acessível e os modelos estão disponíveis."""
        try:
            models = self.client.list()
            available_names = [m.model for m in models.models]
            
            status = {
                "connected": True,
                "embedding_model_ok": self.embedding_model in available_names,
                "rag_model_ok": self.rag_model in available_names,
                "available_models": available_names
            }
            logger.info("Verificação de conexão com Ollama realizada.")
            return status
        except Exception as e:
            logger.warning(f"Ollama offline ou inacessível: {str(e)}")
            return {"connected": False, "error": str(e)}

    def get_gpu_usage(self) -> str:
        """Tenta obter o uso atual da VRAM via nvidia-smi para validação do usuário."""
        try:
            import subprocess
            result = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,nounits,noheader"],
                encoding='utf-8'
            )
            used, total = result.strip().split(',')
            return f"VRAM em uso: {used}MB / Total: {total}MB"
        except Exception:
            return "nvidia-smi não disponível (GPU não detectada ou driver não NVIDIA)."

    def unload_models(self):
        """Descarrega os modelos da VRAM imediatamente."""
        try:
            logger.info("Descarregando modelos da VRAM...")
            # Enviar keep_alive: 0 descarrega o modelo imediatamente no Ollama
            self.client.generate(model=self.embedding_model, prompt='', keep_alive=0)
            self.client.chat(model=self.rag_model, messages=[], keep_alive=0)
            logger.info("VRAM liberada com sucesso.")
            return True
        except Exception as e:
            logger.error(f"Erro ao descarregar modelos: {str(e)}")
            return False

    def describe_image(self, image_path: str) -> str:
        """Extrai descrição técnica de uma imagem usando o modelo multimodal qwen3.5."""
        try:
            import base64
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            prompt = "Descreva detalhadamente esta imagem técnica (screenshot de erro ou diagrama). Extraia textos, nomes de variáveis, nomes de tabelas SQL e a lógica do fluxo se houver."
            
            logger.info(f"Processando imagem Vision: {image_path}")
            response = self.client.chat(
                model=self.rag_model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [base64_image]
                }],
                options={"num_ctx": self.num_ctx}
            )
            # Liberação agressiva de VRAM pós-uso (Hot Unload)
            self.client.chat(model=self.rag_model, messages=[], keep_alive=0)
            return response['message']['content']
        except Exception as e:
            logger.error(f"Erro na análise Vision da imagem {image_path}: {str(e)}")
            return ""
