interface Props {
  onBack: () => void;
  onViewHistory: () => void;
  onViewBarcodes: () => void;
  isStock: boolean;
  preferRent: boolean;
  barcodeView: boolean;
  showCorrection: boolean;
  onToggleCorrection: () => void;
}

export function OverviewHeader({
  onBack,
  onViewHistory,
  onViewBarcodes,
  isStock,
  preferRent,
  barcodeView,
  showCorrection,
  onToggleCorrection,
}: Props) {
  return (
    <div className="overview-header">
      {!isStock && (
        <button type="button" className="link" onClick={onBack}>
          ← Zurück zu allen Gruppen
        </button>
      )}
      {!isStock && (
        <button
          type="button"
          className="btn btn--ghost"
          onClick={onViewHistory}
        >
          Diagramme anzeigen
        </button>
      )}
      <button
        type="button"
        className="btn btn--ghost"
        onClick={onViewBarcodes}
      >
        Barcodes anzeigen
      </button>
      {!isStock && (
        <button
          type="button"
          className={`btn ${showCorrection ? "btn--primary" : "btn--ghost"}`}
          onClick={onToggleCorrection}
        >
          {showCorrection ? "Korrektur schließen" : "Korrektur"}
        </button>
      )}
      {!isStock && (
        <div
          className={`barcode-mode-banner barcode-mode-banner--${preferRent ? "rent" : "return"}`}
        >
          <div className="barcode-mode-banner__label">
            {preferRent ? "AUSLEIHE-MODUS" : "RÜCKGABE-MODUS"}
          </div>
          <div className="barcode-mode-banner__desc">
            {preferRent
              ? (barcodeView ? "Barcode einscannen um auszugeben" : "Mengen eingeben um auszugeben")
              : (barcodeView ? "Barcode einscannen um zurückzunehmen" : "Mengen eingeben um zurückzunehmen")}
          </div>
        </div>
      )}
    </div>
  );
}