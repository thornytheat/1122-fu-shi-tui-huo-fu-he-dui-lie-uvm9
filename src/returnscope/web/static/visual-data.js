function drawProjectChart(target, points) {
    const maxValue = Math.max(...points.map(row=>Math.abs(row.value)), 1);
    const sides = named('div', undefined, 'inspection-pair');
    for (const [index, group] of [points.slice(0,7), points.slice(7)].entries()) {
        const lane = named('section', undefined, 'inspection-lane');
        lane.append(named('h3', index === 0 ? '复核排序前段' : '其余观测'));
        for (const item of group) {
            const strip = named('div',undefined,'comparison-strip');
            const track = named('span',undefined,'comparison-track');
            const amount = named('span',undefined,'comparison-fill');
            amount.style.width = `${Math.abs(item.value) / maxValue * 100}%`;
            track.append(amount);
            strip.append(named('span', item.label),track,named('b',item.value));
            lane.append(strip);
        }
        if (!group.length) lane.append(named('p','本批暂无记录','empty'));
        sides.append(lane);
    }
    target.append(sides);
}
