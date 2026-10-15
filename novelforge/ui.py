from __future__ import annotations

import io
import json
import os
import secrets
import shutil
import zipfile
from pathlib import Path

import streamlit as st

from .config import load_env, write_config
from .llm import OpenAILLM
from .models import StoryFoundation
from .pipeline import ChapterPipeline
from .project import NovelProject

st.set_page_config(page_title="NovelForge", page_icon="📚", layout="wide", initial_sidebar_state="auto")

st.markdown(
    """
<style>
.block-container {max-width: 1180px; padding-top: 1rem; padding-bottom: 3rem;}
[data-testid="stSidebar"] {min-width: 280px;}
@media (max-width: 760px) {
  .block-container {padding: .7rem .75rem 2rem .75rem;}
  [data-testid="stSidebar"] {min-width: 250px; max-width: 88vw;}
  input, textarea, select {font-size: 16px !important;}
  div[data-testid="stMetric"] {padding: .35rem 0;}
}
</style>
""",
    unsafe_allow_html=True,
)

load_env()


def _workspace() -> Path:
    root = os.getenv("NOVELFORGE_WORKSPACE_DIR", "").strip()
    if not root:
        root = str(Path.cwd() / "projects")
    p = Path(root).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _project_dirs() -> list[Path]:
    root = _workspace()
    return sorted([p for p in root.iterdir() if p.is_dir() and (p / "novelforge.db").exists()], key=lambda p: p.name.casefold())


def _safe_slug(name: str) -> str:
    keep = []
    for ch in name.strip():
        if ch.isalnum() or ch in "-_":
            keep.append(ch)
        elif ch.isspace():
            keep.append("-")
    slug = "".join(keep).strip("-")
    return slug or "historia"


def _password_gate() -> None:
    expected = os.getenv("NOVELFORGE_ACCESS_PASSWORD", "").strip()
    if not expected:
        return
    if st.session_state.get("nf_auth"):
        return
    st.title("📚 NovelForge")
    st.caption("Área protegida")
    typed = st.text_input("Senha de acesso", type="password")
    if st.button("Entrar", type="primary", use_container_width=True):
        if secrets.compare_digest(typed, expected):
            st.session_state["nf_auth"] = True
            st.rerun()
        st.error("Senha incorreta.")
    st.stop()


def _backup_bytes(project: NovelProject) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in project.root.rglob("*"):
            if path.is_file() and path.name != ".env":
                z.write(path, path.relative_to(project.root))
    return buf.getvalue()


def _restore(uploaded, workspace: Path) -> Path:
    dest = workspace / f"restaurado-{secrets.token_hex(3)}"
    dest.mkdir(parents=True, exist_ok=True)
    raw = uploaded.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            candidate = (dest / info.filename).resolve()
            if dest.resolve() not in candidate.parents and candidate != dest.resolve():
                raise ValueError("Backup inválido.")
        z.extractall(dest)
    dbs = list(dest.rglob("novelforge.db"))
    if not dbs:
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError("O ZIP não contém um projeto NovelForge.")
    if dbs[0].parent != dest:
        inner = dbs[0].parent
        temp = workspace / f"importado-{secrets.token_hex(3)}"
        shutil.move(str(inner), str(temp))
        shutil.rmtree(dest, ignore_errors=True)
        dest = temp
    return dest


def _api_key_input() -> str | None:
    env_name = "OPENAI" + "_API" + "_KEY"
    configured = bool(os.getenv(env_name, "").strip())
    if configured:
        st.success("Chave da API configurada no servidor.")
        return None
    key = st.session_state.get("nf_api_key", "")
    typed = st.text_input("Chave da API OpenAI", value=key, type="password", help="Fica somente nesta sessão do navegador.")
    if typed != key:
        st.session_state["nf_api_key"] = typed.strip()
    return st.session_state.get("nf_api_key") or None


def _load_json(payload: str):
    try:
        return json.loads(payload)
    except Exception:
        return payload


_password_gate()
workspace = _workspace()

st.sidebar.title("📚 NovelForge")
projects = _project_dirs()
labels = {p.name: p for p in projects}

with st.sidebar.expander("➕ Nova história", expanded=not projects):
    title = st.text_input("Título", key="new_title")
    premise = st.text_area("Premissa", key="new_premise", height=100)
    protagonist = st.text_input("Protagonista", key="new_protagonist")
    genre = st.text_input("Gênero", value="progression fantasy", key="new_genre")
    if st.button("Criar história", type="primary", use_container_width=True):
        if not title.strip():
            st.error("Informe um título.")
        else:
            root = workspace / _safe_slug(title)
            n = 2
            while root.exists():
                root = workspace / f"{_safe_slug(title)}-{n}"
                n += 1
            NovelProject.create(root, StoryFoundation(title=title.strip(), premise=premise.strip(), protagonist=protagonist.strip(), genre=genre.strip()))
            st.session_state["nf_selected"] = root.name
            st.rerun()

projects = _project_dirs()
labels = {p.name: p for p in projects}
if not projects:
    st.info("Crie sua primeira história na barra lateral.")
    st.stop()

selected_default = st.session_state.get("nf_selected")
options = [p.name for p in projects]
idx = options.index(selected_default) if selected_default in options else 0
selected = st.sidebar.selectbox("História", options, index=idx)
st.session_state["nf_selected"] = selected
project = NovelProject(labels[selected])
foundation = project.foundation

st.sidebar.caption(foundation.get("title") or selected)
page = st.sidebar.selectbox(
    "Área",
    ["✍️ Gerar capítulo", "📖 Bíblia", "👤 Personagens", "🧭 Arcos e fios", "🛡️ Continuidade", "✅ Cânone", "🕒 Cronologia", "📚 Capítulos", "🔎 Memória", "💾 Backup", "⚙️ Configurações"],
)

st.title(foundation.get("title") or "NovelForge")
st.caption("Agente de escrita longa com memória persistente e auditoria de continuidade")

if page == "✍️ Gerar capítulo":
    st.subheader(f"Próximo capítulo: {project.next_chapter_number()}")
    api_key = _api_key_input()
    direction = st.text_area("Direção para o capítulo", height=130, placeholder="O que você quer que aconteça? Deixe vazio para o Diretor decidir a partir do estado da história.")
    if st.button("Gerar capítulo", type="primary", use_container_width=True):
        env_name = "OPENAI" + "_API" + "_KEY"
        if not api_key and not os.getenv(env_name, "").strip():
            st.error("Informe sua chave da API OpenAI.")
        else:
            try:
                with st.spinner("Diretor, planejador, escritor e auditores trabalhando..."):
                    model = project.config.get("llm", {}).get("model", "gpt-5.6-sol")
                    result = ChapterPipeline(project, OpenAILLM(model=model, api_key=api_key)).generate(direction)
                st.success(f"Capítulo {result.chapter_number}: {result.title}")
                st.markdown(result.content)
                with st.expander("Plano e auditorias"):
                    st.json({"director": result.director, "plan": result.plan, "critique": result.critique, "continuity": result.continuity, "canon": result.canon})
            except Exception as exc:
                st.error(str(exc))

elif page == "📖 Bíblia":
    st.subheader("Fundação da história")
    premise = st.text_area("Premissa", foundation.get("premise", ""), height=130)
    tone = st.text_input("Tom", foundation.get("tone", ""))
    pov = st.text_input("Ponto de vista", foundation.get("pov", "third-person limited"))
    setting = st.text_area("Mundo / cenário", foundation.get("setting", ""), height=130)
    themes = st.text_area("Temas — um por linha", "\n".join(foundation.get("themes", [])))
    hard = st.text_area("Regras rígidas — uma por linha", "\n".join(foundation.get("hard_rules", [])))
    style = st.text_area("Regras de estilo — uma por linha", "\n".join(foundation.get("style_rules", [])))
    forbidden = st.text_area("Direções proibidas — uma por linha", "\n".join(foundation.get("forbidden", [])))
    if st.button("Salvar Bíblia", type="primary", use_container_width=True):
        project.update_foundation({"premise": premise, "tone": tone, "pov": pov, "setting": setting, "themes": [x.strip() for x in themes.splitlines() if x.strip()], "hard_rules": [x.strip() for x in hard.splitlines() if x.strip()], "style_rules": [x.strip() for x in style.splitlines() if x.strip()], "forbidden": [x.strip() for x in forbidden.splitlines() if x.strip()]})
        st.success("Bíblia salva.")

elif page == "👤 Personagens":
    with st.expander("Adicionar ou atualizar", expanded=True):
        name = st.text_input("Nome")
        summary = st.text_area("Resumo / estado atual", height=120)
        if st.button("Salvar personagem", type="primary", use_container_width=True) and name.strip():
            project.add_entity("character", name.strip(), summary.strip())
            st.success("Personagem salvo.")
    q = st.text_input("Filtrar")
    for e in project.list_entities("character"):
        if q and q.casefold() not in (e["name"] + " " + (e.get("summary") or "")).casefold():
            continue
        with st.expander(e["name"]):
            st.write(e.get("summary") or "Sem resumo.")

elif page == "🧭 Arcos e fios":
    st.subheader("Arcos")
    with st.expander("Adicionar arco"):
        at = st.text_input("Título do arco")
        ag = st.text_input("Objetivo")
        ast = st.text_input("Riscos / stakes")
        asum = st.text_area("Resumo")
        if st.button("Salvar arco", use_container_width=True) and at.strip():
            try:
                project.add_arc(at.strip(), asum.strip(), ag.strip(), ast.strip())
                st.success("Arco salvo.")
            except Exception as exc:
                st.error(str(exc))
    arcs = project.db.query("SELECT title,status,summary,goal,stakes FROM arcs ORDER BY position")
    if arcs:
        st.dataframe(arcs, use_container_width=True, hide_index=True)
    st.subheader("Fios narrativos")
    with st.expander("Adicionar fio"):
        tt = st.text_input("Título do fio")
        td = st.text_area("Descrição")
        imp = st.slider("Importância", 1, 10, 5)
        payoff = st.text_input("Payoff esperado")
        if st.button("Salvar fio", use_container_width=True) and tt.strip():
            project.add_thread(tt.strip(), td.strip(), imp, project.next_chapter_number() - 1, payoff.strip())
            st.success("Fio salvo.")
    threads = project.db.query("SELECT title,status,importance,description,target_payoff,last_mentioned_chapter FROM threads ORDER BY importance DESC,id DESC")
    if threads:
        st.dataframe(threads, use_container_width=True, hide_index=True)

elif page == "🛡️ Continuidade":
    rows = project.db.query("SELECT chapter_number,kind,content_json FROM plans WHERE kind IN ('critique','continuity') ORDER BY chapter_number DESC,id DESC LIMIT 40")
    if not rows:
        st.info("As auditorias aparecem aqui após a geração de capítulos.")
    for row in rows:
        with st.expander(f"Capítulo {row['chapter_number']} · {row['kind']}"):
            st.json(_load_json(row["content_json"]))

elif page == "✅ Cânone":
    facts = project.db.query("SELECT subject_type,subject_name,predicate,value,source_chapter,confidence,canon_status FROM facts ORDER BY id DESC")
    if facts:
        st.dataframe(facts, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum fato canônico registrado ainda.")

elif page == "🕒 Cronologia":
    rows = project.db.query("SELECT chapter_number,event_order,story_time,location,event,consequence FROM timeline ORDER BY chapter_number,event_order,id")
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum evento registrado ainda.")

elif page == "📚 Capítulos":
    chapters = project.chapters()
    if not chapters:
        st.info("Nenhum capítulo gerado ainda.")
    for ch in chapters:
        with st.expander(f"Capítulo {ch['number']}: {ch['title']} · {ch['word_count']} palavras"):
            if ch.get("summary"):
                st.caption(ch["summary"])
            st.markdown(ch["content"])
    if chapters:
        manuscript = project.export_markdown()
        st.download_button("Baixar livro em Markdown", data=manuscript.read_bytes(), file_name="manuscript.md", mime="text/markdown", use_container_width=True)

elif page == "🔎 Memória":
    q = st.text_input("O que você quer encontrar?")
    if q:
        results = project.search(q, 20)
        if not results:
            st.info("Nada encontrado.")
        for row in results:
            with st.expander(f"{row['kind']} · {row['title']}"):
                st.write(row["body"][:5000])

elif page == "💾 Backup":
    st.subheader("Backup portátil")
    st.download_button("Baixar backup completo da história", data=_backup_bytes(project), file_name=f"{project.root.name}-backup.zip", mime="application/zip", use_container_width=True)
    st.divider()
    uploaded = st.file_uploader("Restaurar um backup ZIP", type=["zip"])
    if uploaded and st.button("Restaurar como nova história", use_container_width=True):
        try:
            restored = _restore(uploaded, workspace)
            st.session_state["nf_selected"] = restored.name
            st.success("Backup restaurado.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

elif page == "⚙️ Configurações":
    cfg = project.config
    gen = cfg.setdefault("generation", {})
    words = st.number_input("Palavras alvo por capítulo", min_value=500, max_value=20000, value=int(gen.get("target_words", 2500)), step=250)
    recent = st.number_input("Capítulos recentes no contexto", min_value=1, max_value=20, value=int(gen.get("recent_chapters", 3)))
    retrieval = st.number_input("Memórias recuperadas", min_value=1, max_value=100, value=int(gen.get("retrieval_limit", 12)))
    revision = st.checkbox("Revisão automática", value=bool(gen.get("auto_revision", True)))
    canon = st.checkbox("Confirmar automaticamente fatos aceitos pelo curador", value=bool(gen.get("auto_canon_commit", True)))
    if st.button("Salvar configurações", type="primary", use_container_width=True):
        gen.update({"target_words": int(words), "recent_chapters": int(recent), "retrieval_limit": int(retrieval), "auto_revision": revision, "auto_canon_commit": canon})
        write_config(project.root, cfg)
        project.config = cfg
        st.success("Configurações salvas.")
    st.info("No Android, abra o menu do navegador e use ‘Adicionar à tela inicial’ para ter um atalho como aplicativo.")
