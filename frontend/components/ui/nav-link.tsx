"use client"

import Link from "next/link"
import { type ComponentProps, type MouseEvent } from "react"

type NavLinkProps = ComponentProps<typeof Link> & {
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void
}

export function NavLink({ href, onClick, children, ...props }: NavLinkProps) {
  const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (onClick) {
      onClick(e)
    }
    // Allow default Link behavior (prefetching, etc.)
  }

  return (
    <Link href={href} onClick={handleClick} {...props}>
      {children}
    </Link>
  )
}
