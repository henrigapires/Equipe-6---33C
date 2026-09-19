import { createContext,useContext,useState,type ReactNode } from "react";
import { gradeOptions,turmas,type RotinaPreferencias } from "./grade-data";
type Ctx={selectedIds:string[];setSelectedIds:(v:string[])=>void;gradeName:string;setGradeName:(v:string)=>void;preferencias:RotinaPreferencias;setPreferencias:(v:RotinaPreferencias)=>void};
const GradeContext=createContext<Ctx|undefined>(undefined);
export function GradeProvider({children}:{children:ReactNode}){const [selectedIds,setSelectedIds]=useState(gradeOptions[0]?.ids ?? []);const [gradeName,setGradeName]=useState("Grade 1");const [preferencias,setPreferencias]=useState<RotinaPreferencias>({turno:"Tarde",modalidadePref:"ambas",compromissosFixos:[]});return <GradeContext.Provider value={{selectedIds,setSelectedIds,gradeName,setGradeName,preferencias,setPreferencias}}>{children}</GradeContext.Provider>}
export function useGrade(){const value=useContext(GradeContext);if(!value)throw new Error("useGrade must be inside GradeProvider");return value}
export function getTurmas(ids:string[]){return turmas.filter(t=>ids.includes(t.id))}
