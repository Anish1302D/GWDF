import React, { useMemo, useState } from "react";
import { Search, LocateFixed, Printer } from "lucide-react";

export default function BlockSelector({
  statesList,
  selectedStateCode,
  onSelectState,
  blocks,
  selectedDistrict,
  onSelectDistrict,
  selectedBlockId,
  onSelectBlock,
  onLocateMe,
  locating,
  t,
}) {
  const [searchTerm, setSearchTerm] = useState("");

  const districts = useMemo(() => {
    const set = new Set(blocks.map((b) => b.district));
    return Array.from(set).sort();
  }, [blocks]);

  const filteredBlocks = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    return blocks.filter((b) => {
      const matchDist = !selectedDistrict || b.district === selectedDistrict;
      const matchQuery =
        !q ||
        b.block_name.toLowerCase().includes(q) ||
        b.district.toLowerCase().includes(q) ||
        b.block_id.toLowerCase().includes(q);
      return matchDist && matchQuery;
    });
  }, [blocks, selectedDistrict, searchTerm]);

  return (
      <div className="selector-bar selector-bar-india card no-print">
        <div className="selector-field">
          <label htmlFor="state-select">State / Union Territory</label>
          <select
            id="state-select"
            value={selectedStateCode}
            onChange={(e) => onSelectState(e.target.value)}
          >
            <option value="ALL">🇮🇳 All India (National Map)</option>
            {statesList.map((st) => (
              <option key={st.state_code} value={st.state_code}>
                {st.state} ({st.forecasted_blocks}/{st.total_blocks} blocks)
              </option>
            ))}
          </select>
        </div>

        <div className="selector-field">
          <label htmlFor="district-select">{t.selectDistrict}</label>
          <select
            id="district-select"
            disabled={selectedStateCode === "ALL"}
            value={selectedDistrict}
            onChange={(e) => {
              const nextDist = e.target.value;
              onSelectDistrict(nextDist);
              const firstInDist = blocks.find((b) => !nextDist || b.district === nextDist);
              if (firstInDist) {
                onSelectBlock(firstInDist.block_id);
              }
            }}
          >
            <option value="">{t.allDistricts}</option>
            {districts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>

        <div className="selector-field">
          <label htmlFor="block-select">{t.selectBlock}</label>
          <select
            id="block-select"
            disabled={selectedStateCode === "ALL"}
            value={selectedBlockId || ""}
            onChange={(e) => onSelectBlock(e.target.value)}
          >
            {filteredBlocks.map((b) => (
              <option key={b.block_id} value={b.block_id}>
                {b.block_name} ({b.district}) — {t.riskClasses[b.risk_class] || b.risk_class}
              </option>
            ))}
          </select>
        </div>

        <div className="selector-field selector-search">
        <label htmlFor="block-quick-search">Filter &amp; Actions</label>
        <div className="selector-actions-inline">
          <div className="search-input-wrap">
            <Search size={15} aria-hidden="true" />
            <input
              id="block-quick-search"
              type="search"
              disabled={selectedStateCode === "ALL"}
              placeholder={t.searchBlockPlaceholder}
              value={searchTerm}
              onChange={(e) => {
                const val = e.target.value;
                setSearchTerm(val);
                const q = val.trim().toLowerCase();
                if (q.length >= 2) {
                  const hit = blocks.find(
                    (b) =>
                      (!selectedDistrict || b.district === selectedDistrict) &&
                      b.block_name.toLowerCase().includes(q)
                  );
                  if (hit) {
                    onSelectBlock(hit.block_id);
                  }
                }
              }}
            />
          </div>

          <button
            type="button"
            className="btn-action-compact"
            onClick={onLocateMe}
            disabled={locating}
            title="Detect nearest Indian block via GPS"
          >
            <LocateFixed size={15} />
            <span>{locating ? "Locating…" : "Near Me"}</span>
          </button>

          <button
            type="button"
            className="btn-action-compact"
            onClick={() => window.print()}
            title="Print or save 1-page block advisory PDF"
          >
            <Printer size={15} />
            <span>Advisory PDF</span>
          </button>
        </div>
      </div>
        </div>
        );
}
