import React from 'react'

export default function ReplayModal({event, onClose}: any){
  const videoUrl = `http://localhost:8000/${event.video_path}`
  return (
    <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.6)',display:'flex',alignItems:'center',justifyContent:'center'}}>
      <div style={{width:'80%',background:'#fff',padding:12}}>
        <button onClick={onClose}>Close</button>
        <h3>{event.event_type}</h3>
        <video controls style={{width:'100%'}} src={videoUrl} />
      </div>
    </div>
  )
}
