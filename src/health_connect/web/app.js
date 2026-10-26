/**
 * Health Connect Explorer - Reactive Client Dashboard Logic
 */

(function () {
  'use strict';

  // Global State
  const state = {
    data: null,
    maxBpm: null,
    datePreset: 'all',
    hrSeriesMode: 'all',
    activeTab: 'tab-overview',
    charts: {},
    sortCol: 'date',
    sortAsc: false,
    searchQuery: '',
    theme: document.documentElement.getAttribute('data-theme') || 'dark',
  };

  // DOM Elements
  const elements = {
    loading: document.getElementById('loading-overlay'),
    dbName: document.getElementById('db-name-label'),
    bpmSlider: document.getElementById('bpm-slider'),
    bpmVal: document.getElementById('bpm-val'),
    bpmResetBtn: document.getElementById('bpm-reset-btn'),
    datePresets: document.getElementById('date-presets'),
    themeToggle: document.getElementById('theme-toggle'),
    navTabs: document.querySelectorAll('.tab-btn'),
    panels: document.querySelectorAll('.tab-panel'),

    // KPIs
    avgHr: document.getElementById('kpi-avg-hr'),
    minHr: document.getElementById('kpi-min-hr'),
    days: document.getElementById('kpi-days'),
    dateRange: document.getElementById('kpi-date-range'),
    latestBpm: document.getElementById('kpi-latest-bpm'),
    latestTime: document.getElementById('kpi-latest-time'),

    totalKm: document.getElementById('kpi-total-km'),
    totalRuns: document.getElementById('kpi-total-runs'),
    totalHours: document.getElementById('kpi-total-hours'),
    avgEf: document.getElementById('kpi-avg-ef'),
    avgDrift: document.getElementById('kpi-avg-drift'),
    driftBadge: document.getElementById('kpi-drift-badge'),
    avgCadence: document.getElementById('kpi-avg-cadence'),
    avgStride: document.getElementById('kpi-avg-stride'),

    // Chart Containers
    chartHr: document.getElementById('chart-hr-averages'),
    chartEf: document.getElementById('chart-ef'),
    chartDrift: document.getElementById('chart-drift'),
    chartCadence: document.getElementById('chart-cadence'),
    chartStride: document.getElementById('chart-stride'),

    // Tables
    tableMonthly: document.querySelector('#table-monthly tbody'),
    tableWeekly: document.querySelector('#table-weekly tbody'),
    tableRuns: document.getElementById('runs-table-body'),
    monthlyCount: document.getElementById('monthly-count-badge'),
    weeklyCount: document.getElementById('weekly-count-badge'),
    tableRowCount: document.getElementById('table-row-count'),
    tableSearch: document.getElementById('table-search-input'),

    // Modal
    runModal: document.getElementById('run-modal'),
    modalTitle: document.getElementById('modal-run-title'),
    modalDate: document.getElementById('modal-run-date'),
    modalBody: document.getElementById('modal-body'),
    modalCloseBtn: document.getElementById('modal-close-btn'),
  };

  // Color Palette Tokens
  const colors = {
    dark: {
      bgCard: 'transparent',
      text: '#94a3b8',
      textStrong: '#f8fafc',
      grid: 'rgba(255, 255, 255, 0.06)',
      tooltipBg: 'rgba(15, 23, 42, 0.92)',
      tooltipBorder: 'rgba(255, 255, 255, 0.12)',
    },
    light: {
      bgCard: 'transparent',
      text: '#64748b',
      textStrong: '#0f172a',
      grid: 'rgba(0, 0, 0, 0.06)',
      tooltipBg: 'rgba(255, 255, 255, 0.95)',
      tooltipBorder: 'rgba(0, 0, 0, 0.12)',
    },
    accent: {
      rose: '#f43f5e',
      amber: '#f59e0b',
      emerald: '#10b981',
      cyan: '#06b6d4',
      violet: '#8b5cf6',
      blue: '#3b82f6',
    }
  };

  /** Fetch dataset from Python backend API */
  async function loadData(bpm = state.maxBpm) {
    elements.loading.classList.remove('hidden');
    try {
      const url = bpm ? `/api/data?max_bpm=${bpm}` : '/api/data';
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      const data = await res.json();
      state.data = data;
      renderApp();
    } catch (err) {
      console.error('Failed to load dataset:', err);
      elements.dbName.textContent = 'Error connecting to server';
    } finally {
      setTimeout(() => elements.loading.classList.add('hidden'), 200);
    }
  }

  /** Render UI components */
  function renderApp() {
    if (!state.data) return;

    // Database pill
    elements.dbName.textContent = `${state.data.db_name} (${state.data.summary.days_recorded} days, ${state.data.summary.total_runs} runs)`;

    // Render Overview KPIs
    const s = state.data.summary;
    elements.avgHr.textContent = s.avg_resting_hr ?? '--';
    elements.minHr.textContent = s.min_resting_hr ?? '--';
    elements.days.textContent = s.days_recorded ?? '--';
    elements.latestBpm.textContent = state.data.latest_heartbeat?.bpm ?? '--';
    elements.latestTime.textContent = state.data.latest_heartbeat?.timestamp ?? '';

    // Render Running KPIs
    elements.totalKm.textContent = s.total_distance_km;
    elements.totalRuns.textContent = s.total_runs;
    elements.totalHours.textContent = s.total_duration_hours;
    elements.avgEf.textContent = s.avg_ef ?? '--';
    elements.avgDrift.textContent = s.avg_drift !== null ? (s.avg_drift >= 0 ? `+${s.avg_drift}` : s.avg_drift) : '--';
    if (s.avg_drift !== null) {
      elements.driftBadge.innerHTML = s.avg_drift <= 5.0
        ? '<span class="status-pill good">&le; 5.0% Robust Aerobic Base</span>'
        : '<span class="status-pill decoupled">&gt; 5.0% Noticeable Decoupling</span>';
    }
    elements.avgCadence.textContent = s.avg_cadence ?? '--';
    elements.avgStride.textContent = s.avg_stride_m ?? '--';

    // Render Charts
    renderHeartRateChart();
    renderRunningCharts();

    // Render Sub-tables
    renderAveragesTables();
    renderRunsTable();
  }

  /** Filter data according to active Date Preset */
  function filterByPreset(records, dateKey = 'date') {
    if (state.datePreset === 'all' || !records.length) return records;
    const now = new Date(records[records.length - 1][dateKey]);
    let cutoff = new Date(now);

    if (state.datePreset === '30d') cutoff.setDate(cutoff.getDate() - 30);
    else if (state.datePreset === '6m') cutoff.setMonth(cutoff.getMonth() - 6);
    else if (state.datePreset === '1y') cutoff.setFullYear(cutoff.getFullYear() - 1);

    return records.filter(r => new Date(r[dateKey]) >= cutoff);
  }

  /** Render Resting Heart Rate Multi-Timeframe Chart */
  function renderHeartRateChart() {
    if (!elements.chartHr) return;
    if (!state.charts.hr) {
      state.charts.hr = echarts.init(elements.chartHr);
      window.addEventListener('resize', () => state.charts.hr.resize());
    }

    const t = colors[state.theme];
    const daily = filterByPreset(state.data.heart_rate.daily);
    const weekly = filterByPreset(state.data.heart_rate.weekly);
    const monthly = filterByPreset(state.data.heart_rate.monthly);

    const series = [];

    if (state.hrSeriesMode === 'all' || state.hrSeriesMode === 'daily') {
      series.push({
        name: 'Daily Average',
        type: 'scatter',
        symbolSize: 4.5,
        itemStyle: { color: colors.accent.emerald, opacity: 0.65 },
        data: daily.map(d => [d.date, d.bpm]),
      });
      series.push({
        name: 'Daily Trendline',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 1.2, type: 'dotted', color: colors.accent.emerald, opacity: 0.7 },
        data: daily.map(d => [d.date, d.bpm]),
      });
    }

    if (state.hrSeriesMode === 'all' || state.hrSeriesMode === 'weekly') {
      series.push({
        name: 'Weekly Average',
        type: 'line',
        smooth: 0.25,
        symbolSize: 6,
        lineStyle: { width: 2.5, type: 'dashed', color: colors.accent.amber },
        itemStyle: { color: colors.accent.amber },
        data: weekly.map(w => [w.date, w.bpm]),
      });
    }

    if (state.hrSeriesMode === 'all' || state.hrSeriesMode === 'monthly') {
      series.push({
        name: 'Monthly Average',
        type: 'line',
        smooth: 0.3,
        symbolSize: 8,
        lineStyle: { width: 3.5, color: colors.accent.rose },
        itemStyle: { color: colors.accent.rose },
        data: monthly.map(m => [m.date, m.bpm]),
      });
    }

    const option = {
      backgroundColor: t.bgCard,
      animationDuration: 400,
      tooltip: {
        trigger: 'axis',
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.textStrong, fontSize: 12 },
        formatter: params => {
          if (!params || !params.length) return '';
          let out = `<div style="font-weight:600;margin-bottom:4px">${params[0].value[0]}</div>`;
          params.forEach(p => {
            if (p.seriesName.includes('Trendline')) return;
            out += `<div style="display:flex;align-items:center;gap:6px;justify-content:space-between">
              <span>${p.marker} ${p.seriesName}:</span>
              <strong>${p.value[1].toFixed(1)} BPM</strong>
            </div>`;
          });
          return out;
        }
      },
      toolbox: {
        show: true,
        right: 25,
        top: 6,
        itemSize: 15,
        itemGap: 12,
        iconStyle: {
          borderColor: t.text,
          borderWidth: 1.5,
        },
        emphasis: {
          iconStyle: {
            borderColor: colors.accent.cyan,
          }
        },
        feature: {
          dataZoom: {
            yAxisIndex: 'all',
            xAxisIndex: 'all',
            title: {
              zoom: 'Box Zoom (Drag rectangle over X & Y)',
              back: 'Undo Box Zoom'
            }
          },
          restore: {
            title: 'Reset View (100% Zoom)'
          },
          saveAsImage: {
            title: 'Save Chart as Image',
            pixelRatio: 2
          }
        }
      },
      legend: {
        show: true,
        top: 0,
        textStyle: { color: t.text, fontSize: 12 },
        selected: { 'Daily Trendline': false }
      },
      grid: { left: 50, right: 45, top: 45, bottom: 65 },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: t.grid } },
        splitLine: { lineStyle: { color: t.grid } },
        axisLabel: { color: t.text, fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: 'BPM',
        nameTextStyle: { color: t.text, fontSize: 11 },
        axisLine: { lineStyle: { color: t.grid } },
        splitLine: { lineStyle: { color: t.grid } },
        axisLabel: { color: t.text, fontSize: 11 }
      },
      dataZoom: [
        {
          id: 'hr_inside_x',
          type: 'inside',
          xAxisIndex: 0,
          filterMode: 'filter',
          zoomOnMouseWheel: true,
          moveOnMouseMove: true,
          moveOnMouseWheel: false
        },
        {
          id: 'hr_inside_y',
          type: 'inside',
          yAxisIndex: 0,
          filterMode: 'none',
          zoomOnMouseWheel: 'shift',
          moveOnMouseMove: 'shift'
        },
        {
          id: 'hr_slider_x',
          type: 'slider',
          xAxisIndex: 0,
          bottom: 10,
          height: 22,
          borderColor: t.grid,
          backgroundColor: 'rgba(0,0,0,0.1)',
          fillerColor: 'rgba(99, 102, 241, 0.2)',
          handleStyle: { color: colors.accent.violet },
          textStyle: { color: t.text, fontSize: 10 }
        },
        {
          id: 'hr_slider_y',
          type: 'slider',
          yAxisIndex: 0,
          right: 8,
          width: 18,
          filterMode: 'none',
          borderColor: t.grid,
          backgroundColor: 'rgba(0,0,0,0.1)',
          fillerColor: 'rgba(99, 102, 241, 0.2)',
          handleStyle: { color: colors.accent.emerald },
          textStyle: { color: t.text, fontSize: 10 }
        }
      ],
      series
    };

    state.charts.hr.setOption(option, true);

    if (!state.charts.hr._hasDblClick) {
      state.charts.hr.getZr().on('dblclick', () => {
        state.charts.hr.dispatchAction({ type: 'restore' });
      });
      state.charts.hr._hasDblClick = true;
    }
  }

  /** Render Synchronized Running Charts (EF, Drift, Cadence, Stride) */
  function renderRunningCharts() {
    if (!state.data.running || !state.data.running.length) return;

    const runs = filterByPreset(state.data.running, 'date_short');
    const t = colors[state.theme];

    const chartConfigs = [
      {
        id: 'ef',
        el: elements.chartEf,
        name: 'Efficiency Factor (EF)',
        valKey: 'ef',
        color: colors.accent.emerald,
        unit: 'm/min / bpm',
        digits: 3,
        markLine: null,
      },
      {
        id: 'drift',
        el: elements.chartDrift,
        name: 'Cardiac Drift (%)',
        valKey: 'drift_pct',
        color: colors.accent.violet,
        unit: '%',
        digits: 1,
        markLine: {
          symbol: 'none',
          data: [
            { yAxis: 5.0, lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5 }, label: { formatter: '5% Threshold', color: '#f59e0b' } },
            { yAxis: 0.0, lineStyle: { color: t.text, type: 'dotted', width: 1 }, label: { show: false } }
          ]
        }
      },
      {
        id: 'cadence',
        el: elements.chartCadence,
        name: 'Cadence (SPM)',
        valKey: 'cadence',
        color: colors.accent.cyan,
        unit: 'SPM',
        digits: 1,
        markLine: null,
      },
      {
        id: 'stride',
        el: elements.chartStride,
        name: 'Stride Length (m)',
        valKey: 'stride_m',
        color: colors.accent.blue,
        unit: 'm',
        digits: 2,
        markLine: null,
      }
    ];

    const chartInstances = [];

    chartConfigs.forEach(cfg => {
      if (!cfg.el) return;
      if (!state.charts[cfg.id]) {
        state.charts[cfg.id] = echarts.init(cfg.el);
        window.addEventListener('resize', () => state.charts[cfg.id].resize());
      }
      const chart = state.charts[cfg.id];
      chartInstances.push(chart);

      const isBottom = cfg.id === 'stride';
      const seriesData = runs.map(r => [r.timestamp, r[cfg.valKey], r]);

      const opt = {
        backgroundColor: t.bgCard,
        animationDuration: 400,
        toolbox: {
          show: true,
          right: 25,
          top: 4,
          itemSize: 14,
          itemGap: 10,
          iconStyle: {
            borderColor: t.text,
            borderWidth: 1.5,
          },
          emphasis: {
            iconStyle: {
              borderColor: colors.accent.cyan,
            }
          },
          feature: {
            dataZoom: {
              yAxisIndex: 'all',
              xAxisIndex: 'all',
              title: {
                zoom: 'Box Zoom (Drag rectangle over X & Y)',
                back: 'Undo Box Zoom'
              }
            },
            restore: {
              title: 'Reset View'
            },
            saveAsImage: {
              title: 'Save Chart as Image',
              pixelRatio: 2
            }
          }
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'cross',
            label: {
              backgroundColor: '#334155'
            },
            lineStyle: {
              color: colors.accent.cyan,
              type: 'dashed'
            }
          },
          backgroundColor: t.tooltipBg,
          borderColor: t.tooltipBorder,
          textStyle: { color: t.textStrong, fontSize: 12 },
          formatter: params => {
            if (!params || !params.length) return '';
            const run = params[0].value[2];
            return `<div style="font-weight:700;margin-bottom:6px">${run.date}</div>
              <div style="color:${cfg.color};font-weight:600;margin-bottom:4px">
                ${cfg.name}: ${run[cfg.valKey] !== null ? run[cfg.valKey] + ' ' + cfg.unit : '-'}
              </div>
              <div style="font-size:11px;color:${t.text};display:grid;grid-template-columns:1fr 1fr;gap:4px 12px">
                <span>Dist: <strong>${run.distance_km} km</strong></span>
                <span>Pace: <strong>${run.pace_str}</strong></span>
                <span>Avg HR: <strong>${run.avg_bpm || '-'} bpm</strong></span>
                <span>Max HR: <strong>${run.max_bpm || '-'} bpm</strong></span>
                <span>Duration: <strong>${run.duration_min} min</strong></span>
                <span>Drift: <strong>${run.drift_pct !== null ? (run.drift_pct >= 0 ? '+' : '') + run.drift_pct + '%' : '-'}</strong></span>
              </div>`;
          }
        },
        grid: { left: 55, right: 45, top: 28, bottom: isBottom ? 50 : 25 },
        xAxis: {
          type: 'time',
          axisLine: { lineStyle: { color: t.grid } },
          splitLine: { lineStyle: { color: t.grid } },
          axisLabel: { color: t.text, fontSize: 10 }
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLine: { lineStyle: { color: t.grid } },
          splitLine: { lineStyle: { color: t.grid } },
          axisLabel: { color: t.text, fontSize: 10 }
        },
        dataZoom: [
          // 1. Inside X zoom & pan
          {
            id: `zoom_x_inside_${cfg.id}`,
            type: 'inside',
            xAxisIndex: 0,
            filterMode: 'filter',
            zoomOnMouseWheel: true,
            moveOnMouseMove: true,
            moveOnMouseWheel: false
          },
          // 2. Inside Y zoom & pan (Shift + wheel/drag)
          {
            id: `zoom_y_inside_${cfg.id}`,
            type: 'inside',
            yAxisIndex: 0,
            filterMode: 'none',
            zoomOnMouseWheel: 'shift',
            moveOnMouseMove: 'shift'
          },
          // 3. Vertical Y-slider on right for independent Y scrolling & zooming
          {
            id: `zoom_y_slider_${cfg.id}`,
            type: 'slider',
            yAxisIndex: 0,
            right: 8,
            width: 18,
            filterMode: 'none',
            borderColor: t.grid,
            backgroundColor: 'rgba(0,0,0,0.1)',
            fillerColor: 'rgba(99, 102, 241, 0.2)',
            handleStyle: { color: cfg.color },
            textStyle: { color: t.text, fontSize: 10 }
          },
          // 4. Horizontal X-slider on bottom chart
          ...(isBottom ? [{
            id: 'zoom_x_slider_master',
            type: 'slider',
            xAxisIndex: 0,
            bottom: 6,
            height: 20,
            borderColor: t.grid,
            backgroundColor: 'rgba(0,0,0,0.1)',
            fillerColor: 'rgba(99, 102, 241, 0.2)',
            handleStyle: { color: colors.accent.violet },
            textStyle: { color: t.text, fontSize: 10 }
          }] : [])
        ],
        series: [
          {
            name: cfg.name,
            type: 'line',
            smooth: 0.2,
            data: seriesData,
            lineStyle: { width: 2, color: cfg.color },
            itemStyle: { color: cfg.color },
            markLine: cfg.markLine
          }
        ]
      };

      chart.setOption(opt, true);

      // Double-click to restore view
      if (!chart._hasDblClick) {
        chart.getZr().on('dblclick', () => {
          chart.dispatchAction({ type: 'restore' });
        });
        chart._hasDblClick = true;
      }
    });

    // Multi-chart synchronization across all 4 running plots:
    // 1. Time-axis (X) zoom & pan synchronization
    let isZoomSyncing = false;

    chartInstances.forEach(sourceChart => {
      sourceChart.off('dataZoom');
      sourceChart.on('dataZoom', params => {
        if (isZoomSyncing) return;

        let start, end, startValue, endValue;
        if (params.batch && params.batch.length) {
          const xItem = params.batch.find(b => {
            if (b.dataZoomId && b.dataZoomId.includes('zoom_y')) return false;
            return true;
          });
          if (!xItem) return; // Pure Y zoom - don't sync to other charts
          start = xItem.start;
          end = xItem.end;
          startValue = xItem.startValue;
          endValue = xItem.endValue;
        } else {
          if (params.dataZoomId && params.dataZoomId.includes('zoom_y')) return; // Ignore Y slider events
          start = params.start;
          end = params.end;
          startValue = params.startValue;
          endValue = params.endValue;
        }

        isZoomSyncing = true;
        try {
          chartInstances.forEach(targetChart => {
            if (targetChart === sourceChart) return;
            const action = {
              type: 'dataZoom',
              dataZoomIndex: 0, // Targets X inside zoom
            };
            if (start !== undefined && end !== undefined) {
              action.start = start;
              action.end = end;
            } else if (startValue !== undefined && endValue !== undefined) {
              action.startValue = startValue;
              action.endValue = endValue;
            }
            targetChart.dispatchAction(action);
          });
        } finally {
          isZoomSyncing = false;
        }
      });

      // Synchronize Restore (reset X zoom back to 100% across all 4 charts)
      sourceChart.off('restore');
      sourceChart.on('restore', () => {
        chartInstances.forEach(targetChart => {
          if (targetChart !== sourceChart) {
            targetChart.dispatchAction({
              type: 'dataZoom',
              dataZoomIndex: 0,
              start: 0,
              end: 100
            });
          }
        });
      });

      // 2. Crosshair cursor sync across subplots
      sourceChart.getZr().off('mousemove');
      sourceChart.getZr().on('mousemove', e => {
        const pt = [e.offsetX, e.offsetY];
        if (sourceChart.containPixel('grid', pt)) {
          const gridPt = sourceChart.convertFromPixel('grid', pt);
          const xVal = gridPt[0];
          chartInstances.forEach(targetChart => {
            if (targetChart === sourceChart) return;
            const targetPt = targetChart.convertToPixel('grid', [xVal, 0]);
            if (targetPt && !isNaN(targetPt[0])) {
              targetChart.dispatchAction({
                type: 'showTip',
                x: targetPt[0],
                y: targetChart.getHeight() / 2
              });
            }
          });
        }
      });

      sourceChart.getZr().off('globalout');
      sourceChart.getZr().on('globalout', () => {
        chartInstances.forEach(targetChart => {
          if (targetChart !== sourceChart) {
            targetChart.dispatchAction({ type: 'hideTip' });
          }
        });
      });
    });
  }

  /** Render Monthly and Weekly Summary Tables */
  function renderAveragesTables() {
    if (!state.data.heart_rate) return;

    // Monthly
    const monthly = state.data.heart_rate.monthly || [];
    elements.monthlyCount.textContent = `${monthly.length} months`;
    elements.tableMonthly.innerHTML = monthly.map((m, idx) => {
      const prev = monthly[idx - 1];
      let trendIcon = '<span style="color:#64748b">-</span>';
      if (prev) {
        const diff = m.bpm - prev.bpm;
        if (Math.abs(diff) < 0.2) trendIcon = '<span style="color:#64748b">&plusmn;0.0</span>';
        else if (diff < 0) trendIcon = `<span style="color:#10b981">&darr; ${Math.abs(diff).toFixed(1)}</span>`;
        else trendIcon = `<span style="color:#f43f5e">&uarr; +${diff.toFixed(1)}</span>`;
      }
      return `<tr>
        <td><strong>${m.label || m.date}</strong></td>
        <td class="num-col">${m.bpm.toFixed(1)}</td>
        <td>${trendIcon}</td>
      </tr>`;
    }).join('');

    // Weekly
    const weekly = state.data.heart_rate.weekly || [];
    elements.weeklyCount.textContent = `${weekly.length} weeks`;
    elements.tableWeekly.innerHTML = weekly.slice(-15).reverse().map(w => {
      const pillClass = w.bpm < 70 ? 'good' : (w.bpm > 75 ? 'decoupled' : 'neutral');
      return `<tr>
        <td>${w.label}</td>
        <td class="num-col"><strong>${w.bpm.toFixed(1)}</strong></td>
        <td><span class="status-pill ${pillClass}">${w.bpm.toFixed(1)} BPM</span></td>
      </tr>`;
    }).join('');
  }

  /** Render Running Sessions Explorer Table */
  function renderRunsTable() {
    if (!state.data.running) return;

    let runs = [...state.data.running];

    // Search filter
    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      runs = runs.filter(r => 
        r.date.toLowerCase().includes(q) ||
        r.pace_str.toLowerCase().includes(q) ||
        String(r.distance_km).includes(q)
      );
    }

    // Sort
    runs.sort((a, b) => {
      let va = a[state.sortCol];
      let vb = b[state.sortCol];
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === 'string') return state.sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      return state.sortAsc ? (va - vb) : (vb - va);
    });

    elements.tableRowCount.textContent = runs.length;

    elements.tableRuns.innerHTML = runs.map(r => {
      const driftDisplay = r.drift_pct !== null
        ? `<span class="status-pill ${r.drift_pct <= 5.0 ? 'good' : 'decoupled'}">${r.drift_pct >= 0 ? '+' : ''}${r.drift_pct.toFixed(1)}%</span>`
        : '-';

      return `<tr data-run-id="${r.id}">
        <td><strong>${r.date}</strong></td>
        <td class="num-col">${r.duration_min} min</td>
        <td class="num-col">${r.distance_km.toFixed(2)}</td>
        <td class="num-col"><strong>${r.pace_str}</strong></td>
        <td class="num-col">${r.speed_kmh ? r.speed_kmh.toFixed(1) : '-'}</td>
        <td class="num-col">${r.speed1_kmh && r.speed2_kmh ? `${r.speed1_kmh.toFixed(1)} / ${r.speed2_kmh.toFixed(1)}` : '-'}</td>
        <td class="num-col">${r.avg_bpm ? r.avg_bpm.toFixed(1) : '-'}</td>
        <td class="num-col">${r.hr1 && r.hr2 ? `${r.hr1.toFixed(0)} / ${r.hr2.toFixed(0)}` : '-'}</td>
        <td class="num-col">${r.cadence ? r.cadence.toFixed(1) : '-'}</td>
        <td class="num-col">${r.stride_m ? r.stride_m.toFixed(2) : '-'}</td>
        <td class="num-col"><strong>${r.ef ? r.ef.toFixed(3) : '-'}</strong></td>
        <td class="num-col">${driftDisplay}</td>
        <td><button class="view-btn" data-action="view-run" data-run-id="${r.id}">Inspect</button></td>
      </tr>`;
    }).join('');
  }

  /** Open Run Detail Split Inspector */
  function showRunModal(runId) {
    const run = state.data.running.find(r => r.id === runId);
    if (!run) return;

    elements.modalTitle.textContent = `Running Session #${run.id}`;
    elements.modalDate.textContent = `${run.date} • ${run.distance_km} km in ${run.duration_min} min (Pace: ${run.pace_str})`;

    const isDecoupled = run.drift_pct !== null && run.drift_pct > 5.0;
    const verdictTitle = isDecoupled ? 'Aerobic Decoupling Detected (> 5.0%)' : 'Stable Aerobic Efficiency (≤ 5.0%)';
    const verdictText = isDecoupled
      ? `Cardiac drift of ${run.drift_pct > 0 ? '+' : ''}${run.drift_pct}% indicates efficiency decreased in the second half. Heart rate rose relative to pace, typical when fatigue sets in or aerobic threshold is exceeded.`
      : `Excellent aerobic foundation with only ${run.drift_pct !== null ? run.drift_pct + '%' : '0%'} drift. The cardiovascular system comfortably sustained pace without excessive heart rate drift.`;

    elements.modalBody.innerHTML = `
      <div class="split-comparison-grid">
        <div class="split-card">
          <h5>Half 1 (Start → 50%)</h5>
          <div class="split-row"><span>Speed:</span><strong>${run.speed1_kmh || '-'} km/h</strong></div>
          <div class="split-row"><span>Heart Rate:</span><strong>${run.hr1 || '-'} BPM</strong></div>
          <div class="split-row"><span>Efficiency Factor (EF1):</span><strong>${run.ef1 || '-'}</strong></div>
          <div class="split-row"><span>Cadence:</span><strong>${run.cadence1 || '-'} SPM</strong></div>
          <div class="split-row"><span>Stride Length:</span><strong>${run.stride1_m || '-'} m</strong></div>
        </div>

        <div class="split-card">
          <h5>Half 2 (50% → Finish)</h5>
          <div class="split-row"><span>Speed:</span><strong>${run.speed2_kmh || '-'} km/h</strong></div>
          <div class="split-row"><span>Heart Rate:</span><strong>${run.hr2 || '-'} BPM</strong></div>
          <div class="split-row"><span>Efficiency Factor (EF2):</span><strong>${run.ef2 || '-'}</strong></div>
          <div class="split-row"><span>Cadence:</span><strong>${run.cadence2 || '-'} SPM</strong></div>
          <div class="split-row"><span>Stride Length:</span><strong>${run.stride2_m || '-'} m</strong></div>
        </div>
      </div>

      <div class="verdict-box ${isDecoupled ? 'decoupled' : ''}">
        <div class="verdict-title">${verdictTitle}</div>
        <div class="verdict-text">${verdictText}</div>
      </div>
    `;

    elements.runModal.classList.add('active');
  }

  /** Setup Event Listeners */
  function setupEventListeners() {
    // Navigation Tabs
    elements.navTabs.forEach(btn => {
      btn.addEventListener('click', () => {
        elements.navTabs.forEach(b => b.classList.remove('active'));
        elements.panels.forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const targetId = btn.getAttribute('data-tab');
        document.getElementById(targetId)?.classList.add('active');
        state.activeTab = targetId;

        // Resize charts to container width
        setTimeout(() => {
          Object.values(state.charts).forEach(c => c && c.resize());
        }, 50);
      });
    });

    // Max BPM Slider with debounce
    let bpmTimeout = null;
    elements.bpmSlider.addEventListener('input', e => {
      const val = parseInt(e.target.value);
      elements.bpmVal.textContent = val >= 130 ? 'All' : `${val} BPM`;
      clearTimeout(bpmTimeout);
      bpmTimeout = setTimeout(() => {
        state.maxBpm = val >= 130 ? null : val;
        loadData(state.maxBpm);
      }, 250);
    });

    elements.bpmResetBtn.addEventListener('click', () => {
      elements.bpmSlider.value = 130;
      elements.bpmVal.textContent = 'All';
      state.maxBpm = null;
      loadData(null);
    });

    // Date Presets
    elements.datePresets.addEventListener('click', e => {
      const btn = e.target.closest('.seg-btn');
      if (!btn) return;
      elements.datePresets.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.datePreset = btn.getAttribute('data-preset');
      renderHeartRateChart();
      renderRunningCharts();
    });

    // Heart Rate Series Toggle Pills
    document.getElementById('hr-series-toggle')?.addEventListener('click', e => {
      const pill = e.target.closest('.pill');
      if (!pill) return;
      document.querySelectorAll('#hr-series-toggle .pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.hrSeriesMode = pill.getAttribute('data-series');
      renderHeartRateChart();
    });

    // Table Search
    elements.tableSearch.addEventListener('input', e => {
      state.searchQuery = e.target.value;
      renderRunsTable();
    });

    // Table Sorting
    document.querySelectorAll('.interactive-table th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const col = th.getAttribute('data-sort');
        if (state.sortCol === col) {
          state.sortAsc = !state.sortAsc;
        } else {
          state.sortCol = col;
          state.sortAsc = true;
        }
        renderRunsTable();
      });
    });

    // Table Row Click / Inspect
    elements.tableRuns.addEventListener('click', e => {
      const btn = e.target.closest('[data-action="view-run"]');
      const tr = e.target.closest('tr');
      const runId = btn ? parseInt(btn.getAttribute('data-run-id')) : (tr ? parseInt(tr.getAttribute('data-run-id')) : null);
      if (runId) showRunModal(runId);
    });

    // Modal Close
    elements.modalCloseBtn.addEventListener('click', () => elements.runModal.classList.remove('active'));
    elements.runModal.addEventListener('click', e => {
      if (e.target === elements.runModal) elements.runModal.classList.remove('active');
    });

    // Theme Toggle
    elements.themeToggle.addEventListener('click', () => {
      state.theme = state.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', state.theme);
      renderHeartRateChart();
      renderRunningCharts();
    });
  }

  // Initialize
  setupEventListeners();
  loadData();
})();
