export function Mark({ draw = false }: { draw?: boolean }) {
  return (
    <svg className="mark" data-draw={draw ? "true" : "false"} viewBox="0 0 210 280" aria-hidden="true">
      <path className="mark-stem" pathLength={1} d="M105 6V268" />
      <path className="mark-upper" pathLength={1} d="M105 28C72 12 34 4 12 14C36 26 70 46 105 86" />
      <path className="mark-upper" pathLength={1} d="M105 52L34 20" />
      <path className="mark-upper" pathLength={1} d="M105 28C138 12 176 4 198 14C174 26 140 46 105 86" />
      <path className="mark-upper" pathLength={1} d="M105 52L176 20" />
      <path className="mark-lower" pathLength={1} d="M105 96C64 76 28 86 6 102C32 124 64 152 105 182" />
      <path className="mark-lower" pathLength={1} d="M105 134L36 106" />
      <path className="mark-lower" pathLength={1} d="M105 96C146 76 182 86 204 102C178 124 146 152 105 182" />
      <path className="mark-lower" pathLength={1} d="M105 134L174 106" />
      <path className="mark-ground" pathLength={1} d="M2 268H208" />
    </svg>
  );
}
