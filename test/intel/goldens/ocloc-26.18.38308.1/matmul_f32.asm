L0:
(W)     mov (16|M0)              r127.0<1>:ud  0x0:ud                             
(W)     and (1|M0)               r127.2<1>:ud  r0.0<0;1,0>:ud    0xFFFFFFC0:ud             
(W)     and (1|M0)               r127.0<1>:uw  r0.4<0;1,0>:uw    0xFF:uw             
(W)     add (1|M0)               r127.2<1>:ud  r127.2<0;1,0>:ud  0x20:ud              {I@2}
(W)     add (1|M0)               r127.2<1>:ud  r127.2<0;1,0>:ud  0x0:ud              {I@1}
(W)     mad (1|M0)               r127.0<1>:ud  r127.2<0;0>:ud    r127.0<0;0>:uw    0x80:uw              {I@1}
(W)     mov (8|M0)               r3.0<1>:ud    r1.0<1;1,0>:ud                  
(W)     send.ugm (1|M0)          r1       r127  null:0  0xFF000000            0x6229E500           {A@1,$0} // wr:1+0, rd:2; load.ugm.d32x32t.a32.ca.cc.bti[255]
(W)     and (1|M0)               r127.0<1>:ud  r0.0<0;1,0>:ud    0xFFFFFFC0:ud              {$0.src}
(W)     add (1|M0)               r127.0<1>:ud  r127.0<0;1,0>:ud  0x0:ud              {I@1}
(W)     send.ugm (1|M0)          r4       r127  null:0  0xFF000000            0x6219C500           {I@1,$1} // wr:1+0, rd:1; load.ugm.d32x8t.a32.ca.cc.bti[255]
(W)     mov (16|M0)              r5.0<1>:ud    r0.0<1;1,0>:ud                   {Compacted}
(W)     or (1|M0)                cr0.0<1>:ud   cr0.0<0;1,0>:ud   0x400004C0:ud              {A@1}
(W)     mul (1|M0)               acc0.0<1>:ud  r3.4<0;1,0>:ud    r5.12<0;1,0>:uw  {A@1}
(W)     macl (1|M0)              r41.0<1>:ud   r3.4<0;1,0>:ud    r5.6<0;1,0>:ud   {Compacted}
(W)     mul (1|M0)               acc0.0<1>:ud  r3.4<0;1,0>:ud    r5.12<0;1,0>:uw 
(W)     mach (1|M0)              r6.0<1>:d     r3.4<0;1,0>:ud    r5.6<0;1,0>:ud  
(W)     mul (1|M0)               acc0.0<1>:ud  r3.3<0;1,0>:ud    r5.2<0;1,0>:uw  
(W)     macl (1|M0)              r42.0<1>:ud   r3.3<0;1,0>:ud    r5.1<0;1,0>:ud   {Compacted}
(W)     mul (1|M0)               acc0.0<1>:ud  r3.3<0;1,0>:ud    r5.2<0;1,0>:uw  
(W)     mach (1|M0)              r11.0<1>:d    r3.3<0;1,0>:ud    r5.1<0;1,0>:ud  
        mov (16|M0)              r43.0<4>:uw   r2.0<1;1,0>:uw                   {$0.dst}
        mov (16|M16)             r45.0<4>:uw   r2.16<1;1,0>:uw                 
        mov (16|M0)              r47.0<4>:uw   r1.0<1;1,0>:uw                  
        mov (16|M16)             r49.0<4>:uw   r1.16<1;1,0>:uw                 
(W)     mov (1|M0)               r3.8<2>:ud    r41.0<0;1,0>:ud                  {I@7}
(W)     mov (1|M0)               r3.9<2>:d     r6.0<0;1,0>:d                    {I@7}
(W)     mov (1|M0)               r3.10<2>:ud   r42.0<0;1,0>:ud                  {I@7}
(W)     mov (1|M0)               r3.11<2>:d    r11.0<0;1,0>:d                   {I@7}
        add (16|M0)              r53.0<1>:q    r3.4<0;1,0>:q     r43.0<4;1,0>:uw  {I@3}
        add (16|M16)             r55.0<1>:q    r3.4<0;1,0>:q     r45.0<4;1,0>:uw 
        add (16|M0)              r61.0<1>:q    r3.5<0;1,0>:q     r47.0<4;1,0>:uw  {I@3}
        add (16|M16)             r63.0<1>:q    r3.5<0;1,0>:q     r49.0<4;1,0>:uw 
        add (16|M0)              r57.0<1>:q    r53.0<1;1,0>:q    r3.1<0;1,0>:ud   {I@4}
        add (16|M16)             r59.0<1>:q    r55.0<1;1,0>:q    r3.1<0;1,0>:ud   {I@4}
        add (16|M0)              r65.0<1>:q    r61.0<1;1,0>:q    r3.0<0;1,0>:ud   {I@4}
        add (16|M16)             r67.0<1>:q    r63.0<1;1,0>:q    r3.0<0;1,0>:ud   {I@4}
        mov (16|M0)              r7.0<1>:d     r57.0<2;1,0>:d                   {Compacted,I@4}
        mov (16|M16)             r8.0<1>:d     r59.0<2;1,0>:d                   {Compacted,I@4}
        mov (16|M0)              r12.0<1>:d    r65.0<2;1,0>:d                   {Compacted,I@4}
        mov (16|M16)             r13.0<1>:d    r67.0<2;1,0>:d                   {Compacted,I@4}
        cmp (32|M0)   (lt)f0.0   null<1>:ud    r7.0<1;1,0>:ud    r4.4<0;1,0>:ud   {@3,$1.dst}
        cmp (32|M0)   (lt)f3.0   null<1>:ud    r12.0<1;1,0>:ud   r4.4<0;1,0>:ud   {I@2}
(W)     asr (1|M0)               r3.12<1>:d    r4.4<0;1,0>:d     31:w              
        mov (16|M0)              r9.0<1>:d     r57.1<2;1,0>:d                   {Compacted}
        mov (16|M16)             r10.0<1>:d    r59.1<2;1,0>:d                   {Compacted}
        mov (16|M0)              r14.0<1>:d    r65.1<2;1,0>:d                   {Compacted}
        mov (16|M16)             r15.0<1>:d    r67.1<2;1,0>:d                   {Compacted}
(f0.0)  cmp (32|M0)   (eq)f0.0   null<1>:d     r9.0<1;1,0>:d     r3.12<0;1,0>:d   {I@3}
(f3.0)  cmp (32|M0)   (eq)f3.0   null<1>:d     r14.0<1;1,0>:d    r3.12<0;1,0>:d   {I@2}
(~f0.0) cmp (32|M0)   (lt)f0.0   null<1>:ud    r9.0<1;1,0>:ud    r3.12<0;1,0>:ud 
(~f3.0) cmp (32|M0)   (lt)f3.0   null<1>:ud    r14.0<1;1,0>:ud   r3.12<0;1,0>:ud 
(W)     mov (1|M0)               r4.10<1>:hf   0x1:hf                             
(f0.0)  sel (32|M0)              r33.0<1>:uw   r4.10<0;1,0>:uw   0x0:uw              {F@1}
(f3.0)  sel (32|M0)              r40.0<1>:uw   r4.10<0;1,0>:uw   0x0:uw             
        and (32|M0)   (ne)f1.0   null<2>:uw    r33.0<1;1,0>:uw   r40.0<1;1,0>:uw  {I@1}
(~f1.0) goto (32|M0)                         L1512                  L1512                
L824:
(W)     mul (16|M0)              acc0.0<1>:ud  r7.0<1;1,0>:ud    r4.8<0;1,0>:uw  
        macl (16|M0)             r51.0<1>:ud   r7.0<1;1,0>:ud    r4.4<0;1,0>:ud   {Compacted}
(W)     mul (16|M16)             acc0.0<1>:ud  r8.0<1;1,0>:ud    r4.8<0;1,0>:uw  
        macl (16|M16)            r52.0<1>:ud   r8.0<1;1,0>:ud    r4.4<0;1,0>:ud   {Compacted}
(W)     mul (16|M0)              acc0.0<1>:ud  r7.0<1;1,0>:ud    r4.8<0;1,0>:uw  
        mach (16|M0)             r16.0<1>:d    r7.0<1;1,0>:ud    r4.4<0;1,0>:ud  
(W)     mul (16|M0)              acc0.0<1>:ud  r8.0<1;1,0>:ud    r4.8<0;1,0>:uw  
        mach (16|M16)            r17.0<1>:d    r8.0<1;1,0>:ud    r4.4<0;1,0>:ud  
(W)     mul (16|M0)              acc0.0<1>:d   r7.0<1;1,0>:ud    r3.24<0;1,0>:uw 
        macl (16|M0)             r18.0<1>:d    r7.0<1;1,0>:ud    r3.12<0;1,0>:d  
(W)     mul (16|M16)             acc0.0<1>:d   r8.0<1;1,0>:ud    r3.24<0;1,0>:uw 
        macl (16|M16)            r19.0<1>:d    r8.0<1;1,0>:ud    r3.12<0;1,0>:d  
        add (32|M0)              r16.0<1>:d    r16.0<1;1,0>:d    r18.0<1;1,0>:d   {Compacted,I@1}
(W)     mul (16|M0)              acc0.0<1>:d   r4.4<0;1,0>:ud    r9.0<2;1,0>:uw  
(W)     cmp (32|M0)   (gt)f0.0   null<1>:d     r4.4<0;1,0>:d     0:w              
        macl (16|M0)             r18.0<1>:d    r4.4<0;1,0>:ud    r9.0<1;1,0>:d   
(W)     mul (16|M16)             acc0.0<1>:d   r4.4<0;1,0>:ud    r10.0<2;1,0>:uw 
        macl (16|M16)            r19.0<1>:d    r4.4<0;1,0>:ud    r10.0<1;1,0>:d  
        mov (16|M0)              r69.0<2>:ud   r51.0<1;1,0>:ud                  {Compacted}
        mov (16|M16)             r71.0<2>:ud   r52.0<1;1,0>:ud                  {Compacted}
        add (16|M0)              r69.1<2>:d    r16.0<1;1,0>:d    r18.0<1;1,0>:d   {I@5}
        add (16|M16)             r71.1<2>:d    r17.0<1;1,0>:d    r19.0<1;1,0>:d   {I@4}
(W&f0.0) jmpi                                L1176                                
L1152:
        mov (32|M0)              r20.0<1>:ud   0x0:ud                              {Compacted}
(W)     jmpi                                 L1448                                
L1176:
        shl (16|M0)              r73.0<1>:q    r69.0<1;1,0>:q    2:w               {Compacted,I@5}
        shl (16|M16)             r75.0<1>:q    r71.0<1;1,0>:q    2:w               {Compacted,I@5}
        shl (16|M0)              r81.0<1>:q    r65.0<1;1,0>:q    2:w               {Compacted}
        shl (16|M16)             r83.0<1>:q    r67.0<1;1,0>:q    2:w               {Compacted}
        mov (32|M0)              r20.0<1>:ud   0x0:ud                              {Compacted}
        add (16|M0)              r77.0<1>:q    r73.0<1;1,0>:q    r3.3<0;1,0>:q    {Compacted,I@5}
        add (16|M16)             r79.0<1>:q    r75.0<1;1,0>:q    r3.3<0;1,0>:q    {Compacted,I@5}
        add (16|M0)              r85.0<1>:q    r81.0<1;1,0>:q    r4.0<0;1,0>:q    {Compacted,I@5}
        add (16|M16)             r87.0<1>:q    r83.0<1;1,0>:q    r4.0<0;1,0>:q    {Compacted,I@5}
(W)     mov (1|M0)               r3.13<1>:d    0:w                              
L1264:
(W)     mul (1|M0)               acc0.0<1>:d   r3.13<0;1,0>:d    r4.8<0;1,0>:uw   {I@1}
(W)     macl (1|M0)              r26.0<1>:d    r3.13<0;1,0>:d    r4.4<0;1,0>:d    {Compacted}
(W)     shl (1|M0)               r3.7<1>:q     r3.13<0;1,0>:ud   2:w              
(W)     shl (1|M0)               r4.3<1>:q     r26.0<0;1,0>:d    2:w               {I@2}
        add (16|M0)              r22.0<1>:q    r77.0<1;1,0>:q    r3.7<0;1,0>:q    {Compacted,I@2}
        add (16|M16)             r24.0<1>:q    r79.0<1;1,0>:q    r3.7<0;1,0>:q    {Compacted}
        add (16|M0)              r29.0<1>:q    r85.0<1;1,0>:q    r4.3<0;1,0>:q    {Compacted,I@3}
        add (16|M16)             r31.0<1>:q    r87.0<1;1,0>:q    r4.3<0;1,0>:q    {Compacted}
        send.ugm (32|M0)         r27      r22  null:0  0x0            0x08200580           {I@3,$2} // wr:4+0, rd:2; load.ugm.d32.a64
        send.ugm (32|M0)         r34      r29  null:0  0x0            0x08200580           {I@1,$3} // wr:4+0, rd:2; load.ugm.d32.a64
(W)     add (1|M0)               r3.13<1>:d    r3.13<0;1,0>:d    1:w              
(W)     cmp (32|M0)   (lt)f2.0   null<1>:d     r3.13<0;1,0>:d    r4.4<0;1,0>:d    {I@1}
        sync.nop                             null                             {Compacted,$3.dst}
        mad (32|M0)              r20.0<1>:f    r20.0<1;0>:f      r27.0<1;0>:f      r34.0<1>:f       {Compacted,$2.dst}
(W&f2.0) jmpi                                L1264                                
L1448:
        add (16|M0)              r89.0<1>:q    r69.0<1;1,0>:q    r65.0<1;1,0>:q   {Compacted}
        add (16|M16)             r91.0<1>:q    r71.0<1;1,0>:q    r67.0<1;1,0>:q   {Compacted}
        shl (16|M0)              r93.0<1>:q    r89.0<1;1,0>:q    2:w               {Compacted,I@2}
        shl (16|M16)             r95.0<1>:q    r91.0<1;1,0>:q    2:w               {Compacted,I@2}
        add (16|M0)              r36.0<1>:q    r93.0<1;1,0>:q    r4.1<0;1,0>:q    {Compacted,I@2}
        add (16|M16)             r38.0<1>:q    r95.0<1;1,0>:q    r4.1<0;1,0>:q    {Compacted,I@2}
        send.ugm (32|M0)         null     r36  r20:2  0x0            0x08000584           {A@1,$4} // wr:4+2, rd:0; store.ugm.d32.a64
L1512:
        join (32|M0)                         L1528                                
L1528:
(W)     mov (16|M0)              r127.0<1>:f   r5.0<1;1,0>:f                    {Compacted}
(W)     send.gtwy (1|M0)         null     r127  null:0  0x0            0x02000010           {EOT,F@1,$5} // wr:1+0, rd:0; end of thread
L1552:
(W)     mov (16|M0)              null<1>:ud    0x5551B9AE:ud                             
(W)     mov (16|M0)              null<1>:ud    0x1ECAE4A1:ud                             
(W)     mov (16|M0)              null<1>:ud    0x0:ud                             
(W)     mov (16|M0)              null<1>:ud    0x1:ud                             
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal                
        illegal
