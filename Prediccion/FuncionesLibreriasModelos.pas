unit FuncionesLibreriasModelos;

interface

uses Tipos, TiposArboles, Funciones2Arboles, BoostingCompletoArboles, BoostArboles;



Procedure ObtenerModeloCompletoLibreria(cadenax, cadenay, cadenaz : String);




Procedure LeerModeloPrediccionVector(txtx : Boolean; CadModx : String; vectorx : VectorDouble; nsx : Integer; var salidax : VectorDouble);




Procedure LeerModeloPrediccionFichero(txtx : Boolean; CadModx : String; CadEntx : String; nsx : Integer; CadSalx : String);






implementation



Procedure ObtenerModeloCompletoLibreria(cadenax, cadenay, cadenaz : String);


Var
   prfmx : Integer;          // Profundidad máxima
   minim : Integer;          // Mínimo nº de casos por nodo
   alfamin : Double;         // Ratio mínimo de casos por nodo
   RatImpMin : Double;       // Dismininución mínimo de impureza
   RatMaymin : Double;       // Ratio de casos en la parte mayoritaria

   prd, funI, crt  : Integer;  // prd = 1 predicción, 0 clasificación; funI (impureza) = 0 varianza, 1 Gini; 2 Entropia, 3 XTB; crt = 0 Gain, 1 Ratio
   resH : Integer;           //  Resultado de cada hoja : 0 clase mayoritaria (YC); 1 media aritmética de YR ; 2 : XGB : (-SumGrd)/(SumHes) (con landa)
   inib : Integer;
   Boost, soft : Boolean;

   Gamma, eta, landa : Double;   // Parámetros correctores, gamma : Reduce nº de hojas; landa : penaliza hojas con pocos casos; eta (shinrake) : evita sobreprenizaje al acumular boosters
   ErrorMin : Double;

   m, n, nk, ns : Integer;        // Casos y Variables
   XT : Matriz2Double;    // Matriz de Datos (m x n)  aunque el primer indice es el de variables, luego es un vector de columnas
   YR : VectorDouble;     // Salidas Reales (original)
   YC : VectorEntero;     // Salidas Clase  (original)
   YRM : Matriz2Double;   // Salidas reales cuando hay más de una variable de salida (vector de columnas)

   nIter, nbst : Integer;     // nIter : número de iteraciones; nbst : nº de boosters (en este caso árboles generados), si regresion nbst = nIrer, si clasificación nbst = nIter*nk
   VectBoost : VectorArbol;    // Vector, conjunto de Boosters
   nbstf : Integer;            // nº final de boosters



Procedure ParametrosDisenoArboles1;

begin
   prfmx:=2;
   minim:=3;
   RatImpMin:=0;
   RatMaymin:=0.95;    //0.9;

   //nNodos:=Round(exp((prfmx+1)*ln(2))-1);

   prd:=1;  //0;
   funI:=3;
   crt:=0;
   resH:=2

   // prd = 1 predicción, 0 clasificación; funI (impureza) = 0 varianza, 1 Gini, 2 Entropia, 3 XGB; crt = 0 Gain, 1 Ratio
   //  resH = Resultado de cada hoja : 0 clase mayoritaria (YC); 1 media aritmética de YR (con landa); 2 : XGB : (-SumGrd)/(SumHes)
end;


Procedure IniciarParametrosBoosting1;

begin
   Boost:=TRUE;
   inib:=0;  //2; //0;
   soft:=TRUE;

   // init Valor del booster inicial: 0 media, 1 odds radio, 2 constante (normalmente 0)

   niter:=100;
   ErrorMin:=0.0001;

   Gamma:=0.0;
   landa:=1;
   eta:=0.1;
end;


begin
   ParametrosDisenoArboles1;
   IniciarParametrosBoosting1;
   ns:=4;
   LeerFichero(prd,ns,cadenax,m,n,nk,XT,YR,YC,YRM);
   //TransformarDatos;


   BoostingCompleto(prd,prfmx,minim,RatImpMin,RatMaymin,funI,crt,resH,Boost,inib,soft,niter,ErrorMin,
                    Gamma,landa,eta,nk,n,ns,m,XT,YRM,YR,YC,nbstf,VectBoost);


   GrabarBoosterTxtDou(cadenay,false,nbstf,VectBoost);
   GrabarBoosterTxtDou(cadenaz,true,nbstf,VectBoost)
end;



Procedure LeerModeloPrediccionVector(txtx : Boolean; CadModx : String; vectorx : VectorDouble; nsx : Integer; var salidax : VectorDouble);


Var
   resH : Integer;
   eta : Double;
   ns : Integer;
   VectBoost : VectorArbol;
   nbstf : Integer;



Procedure ParametrosSalida;

begin
   resH:=2;
   eta:=0.1
end;



begin
   ns:=nsx;
   ParametrosSalida;

   LeerBoosterTxtDou(CadModx,Txtx,nbstf,VectBoost);

   PrediccionMR2(eta,resH,nbstf,VectBoost,vectorx,ns,salidax)
end;




Procedure LeerModeloPrediccionFichero(txtx : Boolean; CadModx : String; CadEntx : String; nsx : Integer; CadSalx : String);


Var
   resH : Integer;
   eta : Double;
   ns, nn : Integer;
   VectBoost : VectorArbol;
   nbstf : Integer;

   Fich, Fich1 : Text;
   vector, salida : VectorDouble;



Procedure ParametrosSalida;

begin
   resH:=2;
   eta:=0.1
end;


Procedure LeerPrimeraLinea;

var
   j : Integer;

begin
   j:=0;

   While not eoln(Fich) do
      begin
      SetLength(vector,j+1);
      Read(Fich,vector[j]);
      inc(j)
      end;
   Readln(Fich);

   nn:=j
end;


Procedure LeerSiguenteLinea;

var
   j : Integer;

begin
   j:=0;

   Repeat
      Read(Fich,vector[j]);
      inc(j)
   Until j = nn;

   Readln(Fich)
end;



Procedure GrabarSalida;

var
   s : Integer;

begin
   s:=0;
   Repeat
      write(Fich1,salida[s]:10:5);
      inc(s)
   Until s = ns;
   writeln(Fich1);
end;



begin
   ns:=nsx;
   ParametrosSalida;

   LeerBoosterTxtDou(CadModx,Txtx,nbstf,VectBoost);

   AssignFile(Fich1,CadSalx);
   Rewrite(Fich1);

   AssignFile(Fich,CadEntx);
   Reset(Fich);

   if not eof(Fich) then
      begin
      LeerPrimeraLinea;
      PrediccionMR2(eta,resH,nbstf,VectBoost,vector,ns,salida);
      GrabarSalida;
      end;

   While not eof(Fich) do
      begin
      LeerSiguenteLinea;
      PrediccionMR2(eta,resH,nbstf,VectBoost,vector,ns,salida);
      GrabarSalida;
      end;

   CloseFile(Fich);
   CloseFile(Fich1)

end;





end.
