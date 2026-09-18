import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './styles.css';
import './interaction.css';

const headlineKeys = [
  'headline_text', 'headline_duration', 'headline_x_position', 'headline_y_position',
  'headline_font_size', 'headline_font_name', 'headline_outline_enabled', 'headline_outline_size',
  'headline_text_color', 'headline_background_color', 'headline_background_width',
  'headline_background_height', 'headline_corner_radius',
];
const numericHeadlineKeys = new Set([
  'headline_duration', 'headline_x_position', 'headline_y_position', 'headline_font_size',
  'headline_outline_size', 'headline_background_width', 'headline_background_height', 'headline_corner_radius',
]);

function defaultHeadline(settings) {
  const headline = Object.fromEntries(headlineKeys.map((key) => [key, settings[key]]));
  return { ...headline, headline_text: headline.headline_text || '' };
}

function normalizeHeadline(headline) {
  return Object.fromEntries(Object.entries(headline).map(([key, value]) => {
    if (!numericHeadlineKeys.has(key) || value === '') return [key, value];
    const number = Number(value);
    return [key, Number.isFinite(number) ? number : value];
  }));
}

function CopyNode({ data }) {
  return <article className="flow-node copy-node">
    <span className="node-kicker">CRIATIVO</span>
    <strong>{data.title || 'Copy sem nome'}</strong>
    <p>{data.text || 'Escreva a copy para começar.'}</p>
    <span className="offer-chip">{data.offerName}</span>
    <Handle type="source" position={Position.Right} id="copy-output" className="flow-handle" />
  </article>;
}

function HeadlineNode({ data }) {
  const headline = data.headline;
  const [form, setForm] = useState(headline);
  useEffect(() => setForm(headline), [headline]);
  const change = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const commit = useCallback(() => data.onChange(normalizeHeadline(form)), [data, form]);
  const changeAndCommit = (key, value) => {
    const next = { ...form, [key]: value };
    setForm(next);
    data.onChange(normalizeHeadline(next));
  };
  return <article className={`flow-node headline-node ${data.connected ? 'connected' : ''}`}>
    <Handle type="target" position={Position.Left} id="headline-input" className="flow-handle" />
    <div className="node-heading"><span className="node-kicker">HEADLINE</span><span>{data.connected ? 'VINCULADA' : 'AGUARDANDO LIGAÇÃO'}</span></div>
    <textarea className="nodrag nopan" value={form.headline_text} placeholder="Escreva a headline..." onPointerDown={(event) => event.stopPropagation()} onChange={(event) => change('headline_text', event.target.value)} onBlur={commit} />
    <div className="node-grid">
      <NumberField label="Duração" value={form.headline_duration} min="0.1" step="0.1" suffix="s" onChange={(value) => change('headline_duration', value)} onBlur={commit} />
      <NumberField label="Fonte" value={form.headline_font_size} min="12" max="180" suffix="px" onChange={(value) => change('headline_font_size', value)} onBlur={commit} />
      <NumberField label="Largura" value={form.headline_background_width} min="80" max="720" suffix="px" onChange={(value) => change('headline_background_width', value)} onBlur={commit} />
      <NumberField label="Altura" value={form.headline_background_height} min="30" max="500" suffix="px" onChange={(value) => change('headline_background_height', value)} onBlur={commit} />
      <ColorField label="Fundo" value={form.headline_background_color} onChange={(value) => changeAndCommit('headline_background_color', value)} />
      <ColorField label="Texto" value={form.headline_text_color} onChange={(value) => changeAndCommit('headline_text_color', value)} />
    </div>
  </article>;
}

function NumberField({ label, value, min, max, step = '1', suffix, onChange, onBlur }) {
  return <label className="node-field"><span>{label}</span><div><input className="nodrag nopan" type="number" min={min} max={max} step={step} value={value ?? ''} onPointerDown={(event) => event.stopPropagation()} onChange={(event) => onChange(event.target.value)} onBlur={onBlur} /><em>{suffix}</em></div></label>;
}

function ColorField({ label, value, onChange }) {
  const color = /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#e31b14';
  return <label className="node-field color-node-field"><span>{label}</span><input className="nodrag nopan" type="color" value={color} onPointerDown={(event) => event.stopPropagation()} onChange={(event) => onChange(event.target.value)} /></label>;
}

const nodeTypes = { copy: memo(CopyNode), headline: memo(HeadlineNode) };

function HeadlineStudio() {
  const [state, setState] = useState(null);
  const [activeId, setActiveId] = useState('');
  const [draft, setDraft] = useState(null);
  const draftRef = useRef(null);
  const [previewDraft, setPreviewDraft] = useState(null);
  const [connected, setConnected] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');
  const [status, setStatus] = useState('Carregando criativos...');

  const copies = useMemo(() => (state?.offers || []).flatMap((offer) => (offer.copies || []).map((copy) => ({ ...copy, offerName: offer.name, offerId: offer.id }))), [state]);
  const activeCopy = copies.find((copy) => copy.id === activeId) || copies[0];

  const load = useCallback(async () => {
    const response = await fetch('/api/state');
    if (!response.ok) throw new Error('Não foi possível carregar os criativos.');
    const next = await response.json();
    setState(next);
    const first = next.offers?.flatMap((offer) => offer.copies || [])[0];
    setActiveId((current) => current || first?.id || '');
    setStatus(first ? 'Escolha um criativo para criar ou editar sua headline.' : 'Crie uma copy no workspace antes de criar headlines.');
  }, []);

  useEffect(() => { load().catch((error) => setStatus(error.message)); }, [load]);
  useEffect(() => {
    if (!activeCopy || !state) return;
    const nextDraft = activeCopy.headline ? { ...defaultHeadline(state.settings), ...activeCopy.headline } : null;
    draftRef.current = nextDraft;
    setDraft(nextDraft);
    setPreviewDraft(nextDraft);
    setConnected(Boolean(activeCopy.headline));
  }, [activeCopy?.id, state]);

  useEffect(() => {
    if (!previewDraft?.headline_text?.trim()) { setPreviewUrl(''); return undefined; }
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch('/api/headline-preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...previewDraft, headline_enabled: true }) });
        if (!response.ok) return;
        const url = URL.createObjectURL(await response.blob());
        setPreviewUrl((current) => { if (current) URL.revokeObjectURL(current); return url; });
      } catch (_) { /* The editor remains usable when preview rendering is unavailable. */ }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [previewDraft]);

  const updateHeadlineDraft = useCallback((nextDraft) => {
    draftRef.current = nextDraft;
    setPreviewDraft(nextDraft);
  }, []);
  const updatePreviewControl = useCallback((key, value) => {
    if (!draftRef.current) return;
    updateHeadlineDraft({ ...draftRef.current, [key]: value });
  }, [updateHeadlineDraft]);

  const createHeadline = () => {
    if (!activeCopy || !state) return;
    const nextDraft = defaultHeadline(state.settings);
    draftRef.current = nextDraft;
    setDraft(nextDraft);
    setPreviewDraft(nextDraft);
    setConnected(false);
    setStatus('Arraste o conector da copy até a headline para vincular.');
  };

  const saveHeadline = async () => {
    const headline = draftRef.current;
    if (!activeCopy || !headline || !connected) { setStatus('Conecte a headline ao criativo antes de salvar.'); return; }
    if (!headline.headline_text.trim()) { setStatus('Escreva a headline antes de salvar.'); return; }
    const response = await fetch(`/api/copies/${encodeURIComponent(activeCopy.id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ headline }) });
    if (!response.ok) { const error = await response.json(); setStatus(error.error || 'Não foi possível salvar a headline.'); return; }
    await load();
    setStatus('Headline vinculada e salva neste criativo.');
  };

  const disconnectHeadline = async () => {
    if (!activeCopy?.headline) { setDraft(null); setConnected(false); return; }
    const response = await fetch(`/api/copies/${encodeURIComponent(activeCopy.id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ headline: null }) });
    if (!response.ok) { setStatus('Não foi possível remover a ligação.'); return; }
    await load();
    setDraft(null);
    draftRef.current = null;
    setPreviewDraft(null);
    setConnected(false);
    setStatus('Headline removida deste criativo.');
  };

  const nodes = useMemo(() => {
    if (!activeCopy) return [];
    const copyNode = { id: 'copy', type: 'copy', position: { x: 56, y: 185 }, data: { title: activeCopy.title, text: activeCopy.text, offerName: activeCopy.offerName } };
    if (!draft) return [copyNode];
    return [copyNode, { id: 'headline', type: 'headline', position: { x: 430, y: 150 }, data: { headline: draft, connected, onChange: updateHeadlineDraft } }];
  }, [activeCopy, draft, connected, updateHeadlineDraft]);
  const edges = useMemo(() => connected && draft ? [{ id: 'headline-link', source: 'copy', sourceHandle: 'copy-output', target: 'headline', targetHandle: 'headline-input', type: 'smoothstep', animated: true, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: '#b7f542', strokeWidth: 2.5 } }] : [], [connected, draft]);
  const onConnect = useCallback((connection) => {
    if (connection.source === 'copy' && connection.target === 'headline' && draft) { setConnected(true); setStatus('Ligação criada. Ajuste a headline e salve.'); }
  }, [draft]);

  return <main className="studio-shell">
    <header className="studio-header"><div><span className="eyebrow">WORKSPACE DE CRIATIVOS</span><h1>Headlines</h1><p>Conecte uma headline a cada criativo que precisar dela.</p></div><div className="header-actions"><button className="secondary" onClick={createHeadline} disabled={!activeCopy}>Nova headline</button><button className="primary" onClick={saveHeadline} disabled={!draft || !connected}>Salvar headline</button></div></header>
    <section className="studio-layout">
      <aside className="copy-sidebar"><div className="sidebar-heading"><h2>Copies</h2><span>{copies.length}</span></div><div className="copy-list">{copies.map((copy) => <button className={`copy-picker ${copy.id === activeCopy?.id ? 'active' : ''}`} key={copy.id} onClick={() => setActiveId(copy.id)}><span className="copy-picker-title">{copy.title || 'Copy sem nome'}</span><span>{copy.offerName}</span>{copy.headline && <i>Headline vinculada</i>}</button>)}</div></aside>
      <section className="flow-panel"><div className="flow-toolbar"><span>{activeCopy ? `${activeCopy.offerName} / ${activeCopy.title || 'Copy sem nome'}` : 'Nenhuma copy disponível'}</span>{activeCopy?.headline && <button className="text-button" onClick={disconnectHeadline}>Remover headline</button>}</div><div className="flow-canvas"><ReactFlowProvider><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onConnect={onConnect} fitView fitViewOptions={{ padding: 0.35 }} nodesDraggable={false} nodesConnectable={Boolean(draft)} elementsSelectable={false} proOptions={{ hideAttribution: true }}><Background gap={24} size={1} color="#3a4534" /><Controls showInteractive={false} /></ReactFlow></ReactFlowProvider></div><div className="flow-status">{status}</div></section>
      <aside className="preview-panel"><div><span className="eyebrow">PREVIEW EXATO</span><h2>Vídeo 9:16</h2><p>O overlay usa o mesmo renderizador do vídeo final.</p></div><div className="phone-preview"><div className="preview-scene"></div>{previewUrl && <img src={previewUrl} alt="Prévia da headline" />}</div>{previewDraft && <div className="preview-controls"><NumberField label="Posição X" value={Math.round((previewDraft.headline_x_position ?? .5) * 100)} min="0" max="100" suffix="%" onChange={(value) => updatePreviewControl('headline_x_position', value / 100)} /><NumberField label="Posição Y" value={Math.round((previewDraft.headline_y_position ?? .2) * 100)} min="0" max="100" suffix="%" onChange={(value) => updatePreviewControl('headline_y_position', value / 100)} /><NumberField label="Cantos" value={previewDraft.headline_corner_radius} min="0" max="100" suffix="px" onChange={(value) => updatePreviewControl('headline_corner_radius', value)} /></div>}</aside>
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<HeadlineStudio />);
