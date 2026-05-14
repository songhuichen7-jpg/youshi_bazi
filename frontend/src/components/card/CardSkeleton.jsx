// frontend/src/components/card/CardSkeleton.jsx
export function CardSkeleton() {
  return (
    <div className="card-skeleton" aria-busy="true">
      <div className="shimmer shimmer-name" />
      <div className="shimmer shimmer-tags" />
      <div className="shimmer shimmer-line" />
    </div>
  );
}
