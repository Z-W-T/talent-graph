import { Typography } from "antd";
import { useMemo } from "react";

/** 饼图数据项 */
export interface PieDatum {
  name: string;
  value: number;
}

interface PieChartProps {
  data: PieDatum[];
  /** 画布边长（px） */
  size?: number;
  /** 环宽（px），中间留白用于放总数 */
  thickness?: number;
  /** 圆心下方说明文字 */
  centerLabel?: string;
  /** 超过该数量的分类会合并为「其他」，避免图例过长 */
  maxSlices?: number;
  colors?: string[];
}

const DEFAULT_COLORS = [
  "#1F4E79", "#2E75B6", "#5B9BD5", "#8FAADC", "#A9C6E8",
  "#3C9D9B", "#63B7A6", "#8CCFB8", "#D9A441", "#E4C179",
];

function polar(cx: number, cy: number, r: number, angle: number): [number, number] {
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
}

/** 环形扇区路径：外弧顺时针 + 内弧逆时针，闭合成环带 */
function donutSlice(cx: number, cy: number, rOuter: number, rInner: number,
                    a0: number, a1: number): string {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const [x0, y0] = polar(cx, cy, rOuter, a0);
  const [x1, y1] = polar(cx, cy, rOuter, a1);
  const [x2, y2] = polar(cx, cy, rInner, a1);
  const [x3, y3] = polar(cx, cy, rInner, a0);
  return [
    `M ${x0} ${y0}`,
    `A ${rOuter} ${rOuter} 0 ${large} 1 ${x1} ${y1}`,
    `L ${x2} ${y2}`,
    `A ${rInner} ${rInner} 0 ${large} 0 ${x3} ${y3}`,
    "Z",
  ].join(" ");
}

/**
 * 轻量环形饼图（纯 SVG，无第三方图表依赖）。
 *
 * 数据按数值倒序取前 maxSlices 项，其余合并为「其他」；每段带原生 title 悬停提示，
 * 右侧为图例（名称 / 数量 / 占比）。单分类时退化为完整圆环，避免弧线退化。
 */
export default function PieChart({
  data,
  size = 172,
  thickness = 42,
  centerLabel = "总计",
  maxSlices = 8,
  colors = DEFAULT_COLORS,
}: PieChartProps) {
  const slices = useMemo(() => {
    const sorted = [...data].filter((d) => d.value > 0).sort((a, b) => b.value - a.value);
    const head = sorted.slice(0, maxSlices);
    const restTotal = sorted.slice(maxSlices).reduce((s, d) => s + d.value, 0);
    const merged: PieDatum[] = restTotal > 0 ? [...head, { name: "其他", value: restTotal }] : head;
    const total = merged.reduce((s, d) => s + d.value, 0);
    let angle = -Math.PI / 2;   // 从 12 点方向开始顺时针
    return {
      total,
      items: merged.map((d, i) => {
        const ratio = total > 0 ? d.value / total : 0;
        const from = angle;
        const to = angle + ratio * Math.PI * 2;
        angle = to;
        return { datum: d, color: colors[i % colors.length], from, to, percent: ratio * 100 };
      }),
    };
  }, [data, maxSlices, colors]);

  if (slices.total <= 0) {
    return (
      <div style={{ padding: "32px 0", textAlign: "center" }}>
        <Typography.Text type="secondary">暂无数据</Typography.Text>
      </div>
    );
  }

  const cx = size / 2;
  const cy = size / 2;
  const rOuter = size / 2 - 2;
  const rInner = Math.max(1, rOuter - thickness);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
           role="img" aria-label={centerLabel}>
        {slices.items.length === 1 ? (
          // 单分类：整圆用圆环描边绘制（弧线起止点重合会退化，故不走扇区路径）
          <circle cx={cx} cy={cy} r={(rOuter + rInner) / 2} fill="none"
                  stroke={slices.items[0].color} strokeWidth={rOuter - rInner}>
            <title>{`${slices.items[0].datum.name}：${slices.items[0].datum.value}（100.0%）`}</title>
          </circle>
        ) : (
          slices.items.map((s) => (
            <path key={s.datum.name} d={donutSlice(cx, cy, rOuter, rInner, s.from, s.to)}
                  fill={s.color} stroke="#fff" strokeWidth={1.5}>
              <title>{`${s.datum.name}：${s.datum.value}（${s.percent.toFixed(1)}%）`}</title>
            </path>
          ))
        )}
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize={24} fontWeight={600} fill="#1F4E79">
          {slices.total}
        </text>
        <text x={cx} y={cy + 18} textAnchor="middle" fontSize={12} fill="#8c8c8c">
          {centerLabel}
        </text>
      </svg>

      <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 200, flex: 1 }}>
        {slices.items.map((s) => (
          <div key={s.datum.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: s.color, flexShrink: 0 }} />
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={s.datum.name}>
              {s.datum.name}
            </span>
            <span style={{ color: "#333", fontWeight: 500 }}>{s.datum.value}</span>
            <span style={{ color: "#999", width: 52, textAlign: "right" }}>{s.percent.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
