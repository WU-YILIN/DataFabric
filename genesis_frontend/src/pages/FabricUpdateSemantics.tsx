import { Navigate, useLocation } from 'react-router-dom'

export default function FabricUpdateSemantics() {
  const location = useLocation()
  const next = new URLSearchParams(location.search)
  next.set('tab', 'update-semantics')
  return <Navigate to={`/fabric/planner?${next.toString()}`} replace />
}
