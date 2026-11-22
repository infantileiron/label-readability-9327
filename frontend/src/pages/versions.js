import { chip, empty, formError, formFooter, heading, icon } from '../components/common/ui.js';
import { ORDER } from '../constants/enums.js';
import { store } from '../stores/workspace.js';
import { esc } from '../utils/format.js';

function specimen(version, kind) {
  const isNew = kind === 'new';
  return `<article class="specimen ${isNew ? 'specimen-new' : ''}"><header><span>${isNew ? '易读样张' : '旧版展签'}</span><span class="mono">${esc(version.code)}</span></header>
    <div class="label-proof" style="--label-size:${Number(version.type_pt)}px;--label-leading:${Number(version.line_height)}"><h2>${esc(version.exhibit)}</h2><p>${esc(version.body)}</p></div>
    <footer><span>${esc(version.title)}</span><span>${version.type_pt} pt · ${Number(version.line_height).toFixed(2)} 倍行距</span></footer></article>`;
}

export function versionsPage() {
  const { study, versions, user } = store;
  const controls = user.role === 'analyst' ? `<button type="button" data-edit="study">新建批次</button><button type="button" data-edit="totals" ${study ? '' : 'disabled'}>订正纸表总数</button><button class="primary" type="button" data-edit="version">${icon('plus')} 登记展签</button>` : '';
  const head = heading('展签校样墙', '版本对照', '对照同一件展品的两份文案与排版，确认观众读到的展签。', controls);
  const current = study ? [versions.find(row => row.id === study.old_id), versions.find(row => row.id === study.new_id)] : [];
  const other = versions.filter(row => !current.includes(row));
  return `${head}${study ? `<section class="study-banner"><div><p class="mono">${esc(study.code)} / 测读任务</p><p>${esc(study.reading_task)}</p></div>${chip(`样本修订 R${study.revision}`)}</section>
    ${paperSummary(study)}
    <div class="proof-wall">${specimen(current[0], 'old')}${specimen(current[1], 'new')}</div>
    <div class="foot-action"><span>展签版本登记后保留原文。改稿时请登记新版本。</span><a class="button" href="#pairs">前往配对记录 ${icon('arrow')}</a></div>` : empty('暂无复验批次', '登记同一展品的两个版本后即可发起复验。')}
    ${other.length ? `<section class="registry"><h2>其他已登记版本</h2><div class="version-register">${other.map(row => `<details><summary><b class="mono">${esc(row.code)}</b>　${esc(row.exhibit)} · ${esc(row.title)}</summary><p>${esc(row.body)}</p><small>${row.type_pt} pt · ${Number(row.line_height).toFixed(2)} 倍行距</small></details>`).join('')}</div></section>` : ''}`;
}

function paperSummary(study) {
  const recon = study.reconciliation;
  if (!recon || !recon.registered) {
    return `<p class="warning">尚未登记两份纸表按读序的答对人数，无法与现有答题记录对账。</p>`;
  }
  const rows = recon.groups.map(group => `<tr><td>${ORDER[group.reading_order]}</td><td class="mono">${group.paper_old ?? '—'}</td><td class="mono">${group.observed_old}</td><td class="mono">${group.old_range[0]}–${group.old_range[1]}</td><td class="mono">${group.paper_new ?? '—'}</td><td class="mono">${group.observed_new}</td><td class="mono">${group.new_range[0]}–${group.new_range[1]}</td><td>${group.conflict ? chip('矛盾', 'amber') : chip('相符', 'green')}</td></tr>`).join('');
  const head = recon.conflicts.length
    ? `<div class="conflict-block"><p class="warning">纸表总数与现有答题记录矛盾，无法补齐：</p><ul>${recon.conflicts.map(item => `<li>${esc(item.message)}</li>`).join('')}</ul></div>`
    : `<p class="muted">两组纸表总数都能由现有记录补足，复验将给出精确检验 p 值的上下界。</p>`;
  return `<section class="sheet totals-sheet"><div class="section-title"><h2>纸表与记录对账</h2>${chip(recon.conflicts.length ? '有矛盾' : '可补齐', recon.conflicts.length ? 'amber' : 'green')}</div>
    <div class="table-scroll"><table><thead><tr><th>读序</th><th>旧版纸表</th><th>旧版已记录</th><th>旧版可补范围</th><th>样张纸表</th><th>样张已记录</th><th>样张可补范围</th><th>状态</th></tr></thead><tbody>${rows}</tbody></table></div>${head}</section>`;
}

export function versionForm() {
  return `<form data-form="version"><h2>登记展签</h2><p class="muted">登记时保存当次实物校样的原文、字号与行距。</p>
    <div class="field-grid"><label>版本编号<input name="code" required maxlength="30" pattern="[A-Z0-9][A-Z0-9\\-]{1,29}" placeholder="YA-03"></label><label>版本标题<input name="title" required maxlength="60" placeholder="样张 · 第二次改写"></label></div>
    <label>展品名称<input name="exhibit" value="${esc(store.versions.find(row => row.id === store.study?.new_id)?.exhibit)}" required maxlength="60"></label>
    <label>展签原文<textarea name="body" required minlength="8" maxlength="500" rows="4"></textarea></label>
    <div class="field-grid"><label>字号（pt）<input name="type_pt" type="number" value="24" min="10" max="72" required></label><label>行距倍数<input name="line_height" type="number" value="1.6" min="1" max="3" step="0.01" required></label></div>
    ${formError}${formFooter('保存版本')}</form>`;
}

export function studyForm() {
  const options = store.versions.map(row => `<option value="${row.id}">${esc(row.code)} · ${esc(row.exhibit)} · ${esc(row.title)}</option>`).join('');
  return `<form data-form="study"><h2>新建复验批次</h2><p class="muted">选择同一展品的两个版本，登记纸表按读序记下的答对人数，并写明两次阅读共用的判定标准。</p>
    <div class="field-grid"><label>批次编号<input name="code" required maxlength="30" pattern="[A-Z0-9][A-Z0-9\\-]{1,29}" placeholder="PD-1122"></label><label>展厅／测读点<input name="station" required maxlength="60" placeholder="常设展 · 二厅"></label></div>
    <label>批次名称<input name="title" required maxlength="60"></label>
    <label>测读任务<textarea name="reading_task" required minlength="4" maxlength="240" rows="3"></textarea></label>
    <label>旧版展签<select name="old_id" required><option value="">请选择</option>${options}</select></label>
    <label>易读样张<select name="new_id" required><option value="">请选择</option>${options}</select></label>
    <fieldset class="totals-grid"><legend>纸表答对人数</legend><p class="muted">按读序分别填写旧版与样张答对的人数，缺测不计入。</p>
      <div class="field-grid"><label>先读旧版 · 旧版答对<input name="paper_old_first_old" type="number" min="0" max="1000" required value="10"></label><label>先读旧版 · 样张答对<input name="paper_old_first_new" type="number" min="0" max="1000" required value="15"></label></div>
      <div class="field-grid"><label>先读样张 · 旧版答对<input name="paper_new_first_old" type="number" min="0" max="1000" required value="10"></label><label>先读样张 · 样张答对<input name="paper_new_first_new" type="number" min="0" max="1000" required value="15"></label></div>
    </fieldset>
    ${formError}${formFooter('创建批次')}</form>`;
}

export function totalsForm() {
  const totals = store.study?.paper_totals || {};
  const group = (order, caption) => {
    const row = totals[order] || {};
    return `<div class="field-grid"><label>${caption} · 旧版答对<input name="paper_${order}_old" type="number" min="0" max="1000" required value="${row.old ?? ''}"></label><label>${caption} · 样张答对<input name="paper_${order}_new" type="number" min="0" max="1000" required value="${row.new ?? ''}"></label></div>`;
  };
  return `<form data-form="totals"><h2>订正纸表总数</h2><p class="muted">修改后形成新的样本修订，排队中的任务与历史结果仍使用各自原来的输入。</p>
    <fieldset class="totals-grid"><legend>纸表答对人数</legend>${group('old_first', '先读旧版')}${group('new_first', '先读样张')}</fieldset>
    ${formError}${formFooter('保存总数')}</form>`;
}
