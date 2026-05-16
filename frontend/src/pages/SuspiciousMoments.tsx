import React, {useEffect, useState} from 'react'
import {fetchEvents} from '../services/api'
import ReplayModal from '../components/ReplayModal'

export default function SuspiciousMoments(){
  const [events, setEvents] = useState<any[]>([])
  const [selected, setSelected] = useState<any | null>(null)

  useEffect(()=>{fetchEvents().then(setEvents)}, [])

  return (
    <div>
      <h2>Suspicious Moments</h2>
      <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:12}}>
        {events.map(e=> (
          <div key={e.id} style={{border:'1px solid #ccc',padding:8}} onClick={()=>setSelected(e)}>
            <img src={`http://localhost:8000/${e.thumbnail_path}`} alt="thumb" style={{width:'100%'}} />
            <div>{e.event_type}</div>
            <div>{new Date(e.timestamp).toLocaleString()}</div>
          </div>
        ))}
      </div>
      {selected && <ReplayModal event={selected} onClose={()=>setSelected(null)} />}
    </div>
  )
}
