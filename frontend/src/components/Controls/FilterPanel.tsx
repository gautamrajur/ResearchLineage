interface FilterPanelProps {
  yearRange: [number, number];
  minCitations: number;
  onYearRangeChange: (range: [number, number]) => void;
  onMinCitationsChange: (min: number) => void;
}

export function FilterPanel({
  yearRange,
  minCitations,
  onYearRangeChange,
  onMinCitationsChange,
}: FilterPanelProps) {
  return (
    <div className="flex items-center gap-8 flex-wrap">
      {/* Year Range */}
      <div className="flex items-center gap-3">
        <label className="text-gray-400 text-sm font-medium">Year</label>
        <div className="flex items-center gap-2">
          <span className="text-indigo-400 text-sm font-mono w-10">
            {yearRange[0]}
          </span>
          <input
            type="range"
            min={1997}
            max={2024}
            value={yearRange[0]}
            onChange={(e) =>
              onYearRangeChange([parseInt(e.target.value), yearRange[1]])
            }
            className="
              w-20 h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none
              [&::-webkit-slider-thumb]:w-3
              [&::-webkit-slider-thumb]:h-3
              [&::-webkit-slider-thumb]:bg-indigo-500
              [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:cursor-pointer
              [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(99,102,241,0.5)]
            "
          />
          <span className="text-gray-500">—</span>
          <input
            type="range"
            min={1997}
            max={2024}
            value={yearRange[1]}
            onChange={(e) =>
              onYearRangeChange([yearRange[0], parseInt(e.target.value)])
            }
            className="
              w-20 h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none
              [&::-webkit-slider-thumb]:w-3
              [&::-webkit-slider-thumb]:h-3
              [&::-webkit-slider-thumb]:bg-indigo-500
              [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:cursor-pointer
              [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(99,102,241,0.5)]
            "
          />
          <span className="text-indigo-400 text-sm font-mono w-10">
            {yearRange[1]}
          </span>
        </div>
      </div>

      {/* Divider */}
      <div className="w-px h-6 bg-white/10" />

      {/* Min Citations */}
      <div className="flex items-center gap-3">
        <label className="text-gray-400 text-sm font-medium">Min Citations</label>
        <input
          type="range"
          min={0}
          max={50000}
          step={1000}
          value={minCitations}
          onChange={(e) => onMinCitationsChange(parseInt(e.target.value))}
          className="
            w-28 h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none
            [&::-webkit-slider-thumb]:w-3
            [&::-webkit-slider-thumb]:h-3
            [&::-webkit-slider-thumb]:bg-purple-500
            [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:cursor-pointer
            [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(168,85,247,0.5)]
          "
        />
        <span className="text-purple-400 text-sm font-mono w-14">
          {minCitations.toLocaleString()}
        </span>
      </div>
    </div>
  );
}
