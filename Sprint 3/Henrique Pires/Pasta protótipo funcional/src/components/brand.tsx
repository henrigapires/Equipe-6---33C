const logo = "/logo.png";
export function Brand({compact=false}:{compact?:boolean}){return <img src={logo.url} alt="grade.puc — Simulador de Grade PUC-Rio" className={compact?"h-11 w-auto":"h-auto w-full max-w-sm"}/>}
