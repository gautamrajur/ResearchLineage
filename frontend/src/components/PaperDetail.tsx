import type { Paper } from '../types/paper';

interface PaperDetailProps {
  paper: Paper | null;
}

export function PaperDetail({ paper }: PaperDetailProps) {
  if (!paper) {
    return (
      <div className="p-4 text-gray-500">
        <p>Click a node to see paper details</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <h2 className="text-lg font-semibold text-gray-900 leading-tight">
        {paper.title}
      </h2>

      <div className="space-y-2 text-sm">
        <div>
          <span className="font-medium text-gray-700">Authors:</span>
          <p className="text-gray-600">{paper.authors.join(', ')}</p>
        </div>

        <div className="flex gap-4">
          <div>
            <span className="font-medium text-gray-700">Year:</span>
            <span className="ml-1 text-gray-600">{paper.year}</span>
          </div>
          <div>
            <span className="font-medium text-gray-700">Citations:</span>
            <span className="ml-1 text-gray-600">{paper.citationCount.toLocaleString()}</span>
          </div>
        </div>

        {paper.venue && (
          <div>
            <span className="font-medium text-gray-700">Venue:</span>
            <span className="ml-1 text-gray-600">{paper.venue}</span>
          </div>
        )}
      </div>

      {paper.abstract && (
        <div>
          <span className="font-medium text-gray-700 text-sm">Abstract:</span>
          <p className="text-sm text-gray-600 mt-1 leading-relaxed">
            {paper.abstract}
          </p>
        </div>
      )}

      {paper.url && (
        <a
          href={paper.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-sm text-indigo-600 hover:text-indigo-800"
        >
          View Paper →
        </a>
      )}
    </div>
  );
}
