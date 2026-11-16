import assert from 'node:assert/strict';

export async function selectedDiagnostics(page) {
  const label = await page.locator('#roundLabel').textContent();
  const match = label.match(/^Round (\d+)\b/);
  assert.ok(match, 'The selected diagnostic frame must name its recorded round');
  const rows = async selector => (await page.locator(selector + ' .entry').allTextContents()).map(text => {
    const beginning = text.indexOf('{');
    assert.ok(beginning >= 0, 'Diagnostic entry includes its complete native JSON');
    return JSON.parse(text.slice(beginning));
  });
  return {turn: Number(match[1]) - 1, calls: await rows('#diagnostics'), phases: await rows('#phases')};
}

export function assertFrameDiagnostics(data, frame) {
  assert.deepEqual(frame.calls, data.calls.filter(row => row.turn === frame.turn),
    'Native calls for displayed turn ' + frame.turn);
  assert.deepEqual(frame.phases, data.phases.filter(row => row.turn === frame.turn),
    'Native phases for displayed turn ' + frame.turn);
}

export async function rotateDiagnosticRounds(page, roundCount) {
  // Mutate only the live browser function. Native data and tracked sources stay intact.
  await page.evaluate(rounds => {
    const previous = window.draw;
    const source = previous.toString();
    const callFilter = 'c?.turn===view.turn', phaseFilter = 'p?.turn===view.turn';
    if (!source.includes(callFilter) || !source.includes(phaseFilter)) throw Error('Diagnostic mutation target changed');
    const mutated = source.replace(callFilter, 'c?.turn===(view.turn+1)%' + rounds)
      .replace(phaseFilter, 'p?.turn===(view.turn+1)%' + rounds);
    const replacement = (0, eval)('(' + mutated + ')');
    const slider = document.getElementById('round');
    slider.removeEventListener('input', previous);
    slider.addEventListener('input', replacement);
    window.draw = replacement;
    replacement();
  }, roundCount);
}

export async function assertFinalImage(page, expectedURL) {
  const image = page.locator('#SPECTATOR');
  await image.evaluate(image => image.decode());
  assert.equal(await image.evaluate(image => image.currentSrc || image.src), expectedURL,
    'Final spectator URL must equal the native final artifact URL');
  assert.ok(await image.evaluate(image => image.naturalWidth > 0));
}
