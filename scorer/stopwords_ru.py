"""Built-in Russian stop-word list.

We ship a small, hand-curated list instead of relying on ``nltk.download()``
so the scorer is fully reproducible and works offline — important both for the
defence and for CI. Stop-words are matched on lemmatized form, so only the
infinitive / nominative form of each word needs to appear here.
"""

STOPWORDS_RU = frozenset(
    """
    и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня
    еще нет о из ему теперь когда даже ну вдруг ли если или быть был него до вас нибудь опять уж вам ведь там
    потом себя ничего ей может они тут где есть надо ней для мы тебя их чем был сам чтоб будто под надо ею
    них какие много разве эту моя впрочем хорошо этой этот этих весь слишком таким образом определенный данный
    данный который который чтобы при также более менее очень можно данный также благодаря согласно относительно
    либо вокруг например именно поэтому таким итоге конечный итог свой свойство являться явление год месяц день
    время рабочий работа работа работать опыт стаж требование обязанность обязанность желаемый условие условие
   """
    .split()
)
