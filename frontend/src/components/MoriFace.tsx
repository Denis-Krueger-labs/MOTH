type MoriFaceProps = {
  className?: string
}

function MoriFace({ className = '' }: MoriFaceProps) {
  return (
    <span
      className={`mori-face ${className}`.trim()}
      aria-label="MORI"
    >
      ₍^. .^₎⟆
    </span>
  )
}

export default MoriFace