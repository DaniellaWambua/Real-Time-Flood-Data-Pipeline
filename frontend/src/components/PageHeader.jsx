import "./PageHeader.css";

/**
 * The title/subtitle row every screen opens with, factored out so
 * each page states its own title and subtitle without re-laying-out
 * the row around it.
 */
export default function PageHeader({ title, subtitle }) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        <h1>{title}</h1>
        {subtitle && <p className="page-header-subtitle">{subtitle}</p>}
      </div>
    </div>
  );
}
