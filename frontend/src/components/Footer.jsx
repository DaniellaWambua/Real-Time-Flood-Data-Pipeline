import "./Footer.css";

const CURRENT_YEAR = new Date().getFullYear();

/** The plain footer under every screen. */
export default function Footer() {
  return (
    <footer className="app-footer">
      <span>Strathmore University, BSc Informatics and Computer Science capstone project</span>
      <span>&copy; {CURRENT_YEAR} Daniella Wambua. All rights reserved.</span>
    </footer>
  );
}
