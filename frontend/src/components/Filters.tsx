interface FiltersProps {
  yearRange: [number, number];
  minCitations: number;
  onYearRangeChange: (range: [number, number]) => void;
  onMinCitationsChange: (min: number) => void;
}

export function Filters({
  yearRange,
  minCitations,
  onYearRangeChange,
  onMinCitationsChange,
}: FiltersProps) {
  return (
    <div className="flex items-center gap-6 flex-wrap">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700">Year:</label>
        <span className="text-sm text-gray-600">{yearRange[0]}</span>
        <input
          type="range"
          min={1997}
          max={2024}
          value={yearRange[0]}
          onChange={(e) => onYearRangeChange([parseInt(e.target.value), yearRange[1]])}
          className="w-24 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
        />
        <span className="text-sm text-gray-600">—</span>
        <input
          type="range"
          min={1997}
          max={2024}
          value={yearRange[1]}
          onChange={(e) => onYearRangeChange([yearRange[0], parseInt(e.target.value)])}
          className="w-24 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
        />
        <span className="text-sm text-gray-600">{yearRange[1]}</span>
      </div>

      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700">Min Citations:</label>
        <input
          type="range"
          min={0}
          max={50000}
          step={1000}
          value={minCitations}
          onChange={(e) => onMinCitationsChange(parseInt(e.target.value))}
          className="w-32 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
        />
        <span className="text-sm text-gray-600 w-16">{minCitations.toLocaleString()}</span>
      </div>
    </div>
  );
}
